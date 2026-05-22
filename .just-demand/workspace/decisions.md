# Decisions

## D001: OpenCode-first local workflow

Type: architecture
Scope: workspace
Status: accepted
Date: 2026-05-20
Source Task: none
Supersedes: none

Decision:
Build the first version as an OpenCode-first local framework.

Reason:
The first version should prove the workflow loop before adding multi-platform abstraction, installer polish, or migration machinery.

## D002: Checkpoint commit policy

Type: workflow
Scope: workspace
Status: accepted
Date: 2026-05-22
Source Task: 2026-05-22-checkpoint-commit-after-clean-check-task
Supersedes: none

Decision:
A clean `workflow-check` result (no findings or only fixed low-risk local issues) authorizes an automatic local checkpoint commit. Positive user acceptance remains a valid commit trigger but is secondary. Later corrections use follow-up commits for small fixes or revert commits for fundamentally wrong direction; do not rewrite history by default. Repeated unstable feedback pauses auto-commit until another clean check passes.

Reason:
This balances engineering closure with recoverability. Checkpoint commits after verification provide evidence of verified slices while allowing easy correction via follow-up or revert commits.


## From Task: 2026-05-22-global-just-demand-install-task

- Use global OpenCode installation for reusable runtime assets and explicit project-local initialization for `.just-demand` state.
- Keep plugin writes out of ordinary startup; scripts remain the write path for workflow state.
- First implementation should be local/in-repo CLI behavior, not package publication.
