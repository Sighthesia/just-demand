# just-demand Workflow

主 Agent 负责整个任务；只有在独立验证或疑难决策有明确净收益时才调用子代理。插件只注入状态和提醒，不阻止编辑或其他工具执行。

## 状态机

`no_task -> clarifying -> planned -> implementing -> verifying -> awaiting_user -> completed`

允许的异常路径：

- `awaiting_user -> clarifying`：用户反馈效果偏差，一次只问一个可选择的问题。
- `verifying -> reflecting`：连续两次反馈不正确或长期无法解决，停止修改并调用 advisor。
- 任意未完成状态 -> `paused`：会话结束但任务没有正式关闭。
- `paused -> clarifying|planned|implementing|verifying`：下一次会话恢复任务后重新激活。

## 主 Agent 执行准则

1. 新需求先复述目标，再用结构化问题逐步澄清；不得直接实现模糊需求。
2. 澄清后输出用户可理解的布局图、时序图或范围表，并等待确认。
3. 确认后用脚本创建任务契约，记录用户预期、边界、验收方式和冲突风险；未创建任务时仍可继续工作，但应明确意识到缺少持久上下文。
4. 实现过程中汇报可见效果，不把代码细节作为主要沟通内容。
5. 实现后运行与验收标准匹配的检查；tester 不得重新定义需求。
6. 验证通过后建议进入 `awaiting_user`，让用户检查效果；确认后运行 `task.py finish`，默认自动创建只包含当前任务范围的 checkpoint commit。只有明确不需要提交时才使用 `--no-commit`。脚本只提示非标准状态迁移，不阻止继续执行。
7. 任何失败都要记录原因和下一步，不得用“应该可以”代替验证。

## 子代理边界

- `tester`：只验证当前任务，可做低风险修复，不扩大范围。
- `advisor`：只分析需求、设计、实现、验证或上下文污染的根因，不直接写代码。
- 旧 `researcher`/`coder` 仅在兼容旧任务或用户明确指定时使用。
