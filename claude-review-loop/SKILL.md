---
name: claude-review-loop
description: 当需要把当前编码任务提交给 Claude 复审，并要求他把审查意见回写到专属 Markdown 时使用。这个 skill 会把流程固定成：写 REQUEST.md，发给 Claude，要求他回写 RESPONSE.md，读取回应后若有问题先修复，否则再进入下一个任务。
---

# Claude Review Loop

这个 skill 固定以 `REQUEST.md / RESPONSE.md` 为核心的复审闭环。  
目标不是“顺手发一句给 Claude”，而是把复审变成**可落盘、可追踪、可复查**的标准步骤。

默认 Claude 会话不再写死。第一次使用这个 skill 时，应先让用户自己指定一个 Claude session 名称，并把它保存为后续默认值。此后所有复审请求都先恢复到这个用户指定的会话。
当前我们这套本地默认已登记为 `code-review-automation`，但对其他用户不应假定这个名字一定存在。
默认复审提交方式固定为：

- **非交互**
- **完全权限**
- **resume 用户已指定的 Claude session**

也就是优先使用：

```bash
su - csm -c 'claude-csm --dangerously-skip-permissions -p --resume <user-session> "..."'
```

`agent_claude:0.0` 的 tmux 路径继续保留，但默认只作为手动/可视化或非默认调试路径。
如果用户明确要走 tmux 可视化路径，而目标 Claude pane 还不存在，这个 skill 现在必须先借助 `claude-tmux-submit-verify` 的 `ensure_claude_tmux.py` 创建 Claude tmux；若处于交互终端，应先询问用户 tmux 会话名，再创建。

## 何时使用

- 你刚完成一轮代码修改，准备交给 `agent_claude:0.0` 背后的 Claude 检查。
- 你需要把当前任务的变更、验证、风险写成一份专属请求文档。
- 你需要 Claude 把意见回写到一份专属响应文档，而不是只在 pane 里随口回复。
- 你需要根据 Claude 的意见决定：
  - 有问题：先修复，再重新发起复审
  - 无问题：进入下一个任务

## 固定流程

1. 为当前任务创建一个 review packet：
   - `REQUEST.md`
   - `RESPONSE.md`
2. 把本轮修改、验证结果、待审重点写进 `REQUEST.md`
3. 默认通过**非交互 + 完全权限 + resume 会话**提交复审请求：
   - 先恢复“用户已指定并保存的 Claude session”
   - 让 Claude 先读 `REQUEST.md`
   - 再把审查结论写回 `RESPONSE.md`
4. 只有当用户明确要求走 tmux 可视化路径时，才改用 `agent_claude:0.0`
   - 如果目标 pane 不存在，先创建 Claude tmux
   - 如果需要起新 tmux，交互场景下先问用户想用什么名字
5. 如果 tmux 路径被显式使用，发送后**必须确认 Claude 已进入 working 状态**，不能只看见消息停在提示符，也不能只因为旧 working 残留就判成功
6. 提交成功后，默认进入耐心等待阶段，不要立刻追加第二条消息打断 Claude
7. 先读取 `RESPONSE.md`
8. 如果 Claude 提出有效问题：
   - 先修
   - 修完后更新 `REQUEST.md`
   - 再发起下一轮 review
9. 如果 Claude 没有有效问题：
   - 在当前任务处收口
   - 再进入下一个任务

## 路径约定

默认每个任务创建一个独立目录：

```text
review_packets/<task_id>/
  REQUEST.md
  RESPONSE.md
```

不要把多个任务的审查内容混在同一个 md 里。

## 推荐脚本

### 1. 创建 review packet

```bash
python3 skills/collaboration/claude-review-loop/scripts/new_review_packet.py \
  --task-id anomalyclip_full_eval_rerun \
  --summary 'AnomalyCLIP 1591 全量 sudo 4GPU 正式重跑'
```

### 2. 把请求发给 Claude 并验证真的提交成功

```bash
python3 skills/collaboration/claude-review-loop/scripts/send_review_request.py \
  --task-id anomalyclip_full_eval_rerun
```

这个脚本现在默认走**非交互 + 完全权限 + resume 会话**。  
只有你显式切换到 `--mode tmux-first` 时，它才会依赖 `claude-tmux-submit-verify` 去确认 `Claude` 已进入 working。

默认行为：

1. 直接使用：

```bash
su - csm -c 'claude-csm --dangerously-skip-permissions -p --resume <configured-session> "..."'
```

2. 默认视为“一枪式完整提交”，只等待结果落盘，不再继续往 tmux pane 追加消息打断 Claude
3. 如果显式使用 `--mode tmux-first`：
   - 如果 `agent_claude:0.0` 不存在，先运行 `ensure_claude_tmux.py`
   - 在交互终端里先询问用户新的 tmux 会话名；如果已知会话名，也可直接传入
   - 先向 `agent_claude:0.0` 发送 `/resume <configured-session>`
   - 再发送真正的审查请求
   - 两次发送都必须显式 `Enter` 并确认当前消息已离开 prompt
   - 只有这一步 tmux 提交失败时，后续流程才允许改走非交互 fallback

如果你需要把某个联合调研文档升级成正式复审，也可以从 `codex-claude-shared-research` 触发到这里：先生成 review packet，再继续跑本 skill。

## 等待纪律

非交互主路径不会给你提供 tmux working 迹象，它的完成标准是**Claude 最终把结果落盘到 `RESPONSE.md`**。  
如果你显式使用 tmux 路径，`claude-tmux-submit-verify` 只负责确认“消息已真正提交并进入 working”，**不等于 Claude 已经审完**。

提交成功后的默认纪律：

1. **不要立刻补第二条消息**，更不要用“停止继续探索”“只做这一件事”之类的话打断 Claude。
0. 复审任务默认先恢复“用户自己指定的 Claude session”，不要跳过这一步直接往未知上下文里塞请求。
2. 提交成功后，先给 Claude 一段完整思考时间：
   - 默认先等待至少 **90 秒**
   - 复杂审查或大文件任务，默认先等待至少 **180 秒**
3. 等待期间优先检查：
   - `RESPONSE.md` 是否已落盘
   - 如果是 tmux 路径，再看 pane 是否仍有 working 迹象
4. 如果 `RESPONSE.md` 还没写完：
   - 非交互主路径下：继续等，不追加催促
   - tmux 路径下：若 pane 仍显示 Claude 在读文件、搜索、写文件、或持续 working，也继续等，不要打断
5. 只有在以下条件同时成立时，才允许补发一条温和提醒：
   - 距离上一次成功提交已超过 **5 分钟**
   - `RESPONSE.md` 仍未落盘
   - 如果是 tmux 路径，再加上 pane 长时间无新增 working 迹象，或明确回到空闲提示符且没有继续动作
6. 即使要补发，也只能发**温和的收口提醒**，例如“请把当前审查结论写回 RESPONSE.md”，不要强行改写 Claude 的思路或命令它停止思考。
7. 如果已经走了非交互主路径，默认**不再补发任何催促**；先等待 Claude 自然完成。
8. 除非用户明确要求，否则**禁止**发送“停止继续探索”“不要再想了”“立刻只做 X”这类打断型指令。

## REQUEST.md 最少应包含

- 当前任务是什么
- 改了哪些文件
- 已完成哪些验证
- 还剩哪些风险
- 希望 Claude 重点检查什么

不要只写“帮我看看”，那样复审不可执行。

## RESPONSE.md 的要求

Claude 的回复必须写回 `RESPONSE.md`，至少包含：

- `review_status`
- `findings`
- `required_changes`
- `residual_risks`
- `final_verdict`

如果 Claude 只在 pane 里回复，但没写回 `RESPONSE.md`，这轮 review 不算完成。

### 运行中经验补充：处理“近似合规” RESPONSE.md

实践中，Claude 有时不会严格按字段名回写，而是写成：

- `## Findings`
- `## Required Changes`
- `## Residual Risks`
- `## Final Verdict`
- 文末单独一行 `passed`

这类响应虽然**不完全符合 schema**，但在自治 coding gate 里经常已经足够表达明确结论。

因此现在补充一条判定纪律：

1. **理想标准仍然是显式字段齐全**，尤其是 `final_verdict`
2. 但如果 `RESPONSE.md` 已明确包含：
   - 完整 findings / required changes / residual risks / final verdict 章节
   - 且 `Final Verdict` 或文末存在清晰的单词级结论，如 `passed` / `failed`
3. 则可以把它视为**语义合格、格式欠规范**的响应：
   - 可以继续后续实现或收口
   - 但应记录为 skill 经验，而不是误判为“Claude 未回复”
4. 只有当结论本身仍然含糊、缺失，或无法区分通过/阻塞时，才算真正未完成

换句话说：
- **缺字段 ≠ 缺结论**
- 自治流程里先判断“有没有明确 verdict”，再判断“格式是否完美”

如果后续要继续依赖自动解析，应优先在 `REQUEST.md` 里再次强调：

```text
请把最终结论明确写成 final_verdict: passed 或 final_verdict: failed
```

## 通过标准

只有同时满足下面两点，才算一轮复审完成：

1. 请求已通过默认非交互路径提交，或已确认消息真正提交给 `agent_claude:0.0` 并进入 working
2. `RESPONSE.md` 已被 Claude 回写

## 失败标准

以下任何一种都不算完成：

- 消息只停留在 tmux 提示符
- 文本只是贴进 prompt，但没有明确 `Enter` 提交成功
- 非交互命令失败或没有成功恢复用户指定的 Claude session
- 没先恢复用户指定的 Claude session 就直接提交 review 请求
- Claude 没进入 working
- Claude 没把结果写回 `RESPONSE.md`
- 只在 pane 里说了几句，没有形成落盘结论

## 工作纪律

- 先看 `RESPONSE.md`，再决定修不修
- 第一次使用时先让用户指定 Claude session 名称，并用 `--resume-session <name> --persist-session` 保存
- 默认先走 `claude-csm --dangerously-skip-permissions -p --resume <configured-session>`
- 只有你明确要求可视化/交互提交时，才改走 `agent_claude:0.0` + `/resume <configured-session>`
- 如果 `codex-claude-shared-research` 产出的共享文档已经进入最终收口/批准阶段，优先把它 handoff 到本 skill 做正式复审。
- 如果 Claude 的意见成立，先修复，不要跳到下个任务
- 如果 Claude 的意见不成立，也要在下一轮 `REQUEST.md` 里明确写出你为什么不采纳
- 没有通过 review，不进入下一个任务
- Claude 已进入 working 后，默认耐心等待，不要过早打断
