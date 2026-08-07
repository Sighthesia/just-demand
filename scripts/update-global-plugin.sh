#!/usr/bin/env bash
set -euo pipefail

# Register this checkout as an OpenCode global plugin. The plugin keeps its
# source path, so updating the checkout is enough; no files are copied.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
config_file="${OPENCODE_CONFIG_FILE:-${XDG_CONFIG_HOME:-${HOME}/.config}/opencode/opencode.jsonc}"
dry_run=false

usage() {
  printf '用法: %s [--config PATH] [--dry-run]\n' "$0"
}

while (($#)); do
  case "$1" in
    --config)
      (($# >= 2)) || { usage >&2; exit 2; }
      config_file="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$config_file" ]]; then
  printf '错误: 找不到 OpenCode 全局配置: %s\n' "$config_file" >&2
  exit 1
fi

REPO_ROOT="$repo_root" CONFIG_FILE="$config_file" DRY_RUN="$dry_run" python3 - <<'PY'
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

repo = str(Path(os.environ["REPO_ROOT"]).resolve())
config = Path(os.environ["CONFIG_FILE"]).expanduser().resolve()
text = config.read_text(encoding="utf-8")

# Match only a top-level plugin array. This intentionally preserves JSONC
# comments, trailing commas, indentation, and unrelated configuration.
match = re.search(r'(?m)^(?P<indent>[ \t]*)"plugin"\s*:\s*\[(?P<body>[\s\S]*?)\n(?P=indent)\]', text)
entry = json_string = '"' + repo.replace('\\', '\\\\').replace('"', '\\"') + '/.opencode/plugins/just-demand.js"'

if entry in text:
    print(f"已是最新注册路径: {repo}")
    raise SystemExit(0)
if match:
    body = match.group("body")
    indent = match.group("indent") + "  "
    new_body = body.rstrip()
    separator = "," if new_body and not new_body.rstrip().endswith(",") else ""
    replacement = f'{match.group("indent")}"plugin": [{new_body}{separator}\n{indent}{entry}\n{match.group("indent")}]'
    updated = text[:match.start()] + replacement + text[match.end():]
else:
    closing = text.rfind("}")
    if closing < 0:
        raise SystemExit("错误: 全局配置不是有效的 JSONC 对象")
    before = text[:closing].rstrip()
    comma = "" if before.endswith(",") else ","
    updated = f'{before}{comma}\n  "plugin": [{entry}]\n{text[closing:]}'

if os.environ.get("DRY_RUN") == "true":
    print(f"将注册全局插件: {repo}")
    print(f"配置文件: {config}")
    raise SystemExit(0)

backup = config.with_name(config.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
shutil.copy2(config, backup)
config.write_text(updated, encoding="utf-8")
print(f"已更新全局插件: {repo}")
print(f"配置文件: {config}")
print(f"备份文件: {backup}")
print("请重启 OpenCode 使插件加载新版本。")
PY
