import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const pluginDir = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.resolve(pluginDir, "../..");

function sessionKey(raw) {
  raw = raw || process.env.JUST_DEMAND_SESSION_ID || process.env.OPENCODE_SESSION_ID || "default";
  return raw.replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 120) || "default";
}

function readSession(projectRoot, id) {
  try {
    const stateDir = path.join(projectRoot, ".just-demand", "runtime", "sessions");
    const exact = path.join(stateDir, `${sessionKey(id)}.json`);
    const fallback = path.join(stateDir, "default.json");
    const target = fs.existsSync(exact) ? exact : fallback;
    return JSON.parse(fs.readFileSync(target, "utf8"));
  } catch {
    return null;
  }
}

function workflowState(projectRoot, id) {
  const session = readSession(projectRoot, id);
  if (!session?.task) return { status: "no_task", task: null, conflicts: [] };
  const script = path.join(pluginRoot, ".just-demand", "scripts", "task.py");
  const result = spawnSync("python3", [script, "status", session.task], {
    cwd: projectRoot,
    env: { ...process.env, JUST_DEMAND_ROOT: projectRoot },
    encoding: "utf8", timeout: 3000,
  });
  if (result.status !== 0) return { status: "no_task", task: null, conflicts: [] };
  try {
    const task = JSON.parse(result.stdout);
    return { ...task, conflicts: session.conflicts || task.conflicts || [] };
  } catch { return { status: "no_task", task: null, conflicts: [] }; }
}

export const JustDemandPlugin = async ({ directory }) => ({
  config: async (config) => {
    config.skills = config.skills || {};
    config.skills.paths = config.skills.paths || [];
    const skills = path.join(pluginRoot, ".just-demand", "skills");
    if (!config.skills.paths.includes(skills)) config.skills.paths.push(skills);
  },

  "experimental.chat.messages.transform": async (input, output) => {
    if (!output.messages.length) return;
    const state = workflowState(directory, input.sessionID);
    const instruction = `just-demand workflow is active. Current state: ${state.status}. ` +
      (state.task ? `Task: ${state.task}. Follow .just-demand/workflow.md and the matching skill.` :
        "No active task is recorded. Clarify and create a task when the work benefits from task tracking.");
    const conflictReminder = state.conflicts?.length
      ? `\n并发任务提醒：${state.conflicts.map((item) => `${item.task} (${item.files.join(", ")})`).join("；")}。请确认文件边界，必要时与其他 session 协调。`
      : "";
    const firstUser = output.messages.find((message) => message.info?.role === "user");
    if (!firstUser || firstUser.parts?.some((part) => part.type === "text" && part.text.includes("just-demand workflow is active"))) return;
    const reference = firstUser.parts?.[0];
    if (reference) firstUser.parts.unshift({ ...reference, type: "text", text: `<workflow-state>\n${instruction}${conflictReminder}\n</workflow-state>` });
  },
});

export default JustDemandPlugin;
