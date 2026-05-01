---
name: claude-tmux-submit-verify
description: 当需要通过 tmux 给 Claude 会话发消息时使用。要求必须在 send-keys 回车后，再次 capture-pane 并确认 Claude 已进入 working 状态，才允许宣称“已发给 Claude”；若只看到消息停在提示符而没有 working 迹象，则必须判定为未成功提交。
---

# Claude Tmux Submit Verify

这个 skill 只处理一件事：**给 `agent_claude:0.0` 的 tmux pane 发消息时，不能把“文本贴进 prompt”当成成功，必须显式提交 Enter，并看到 Claude 已开始工作。**

默认 tmux 目标固定为 `agent_claude:0.0`。除非用户明确指定别的 Claude pane，否则所有发送与校验都先使用这个目标。
如果当前任务属于代码复审工作流，默认还要先恢复“用户自己指定并保存的 Claude session”，再发送真正的审查请求。
如果目标 pane 不存在，这个 skill 现在还负责**确保 Claude tmux 存在**：优先询问用户想用什么 tmux 会话名，然后新开一个 Claude tmux，再继续后续提交与校验。

## 何时使用

- 你要通过 `tmux` 给 `agent_claude:0.0` 发审核请求、交接说明、复核指令。
- 你准备在聊天里说“我已经发给 Claude 了”。
- 你怀疑消息只是停在提示符，没有真正提交。

## 硬规则

1. 默认通过 `sudo -n tmux` 操作 `agent_claude:0.0`。
1.5. 如果是 review loop，默认先发送 `/resume <configured-session>`，再发送真正消息；不要把 review 请求直接打到未知上下文里。
2. 发送必须采用“`load-buffer -> paste-buffer -> 明确 send-keys C-m`”三步法，不能只依赖一次不稳定的 `send-keys 'message' C-m`。
3. 发送后必须再次 `capture-pane`。
4. 只有满足下面任一条件，才算发送成功：
   - **本次发送之后新增的输出**里出现了新的工作迹象，例如 `●`、`⏺`、`✻`、`Bash(`、`Read(`、`Write(`、`esc to interrupt` 等；
   - 或本次发送之后新增的输出已经明确离开空闲提示符 `❯`，且新增内容不只是消息回显。
5. 如果发送后仍只看到消息停在 `❯` 提示符，不算成功。
6. 如果第一次未确认成功，最多补一次额外 `Enter`，然后再次验证。
7. 如果仍未进入 working，必须明确汇报“未确认提交成功”，不能说“已发给 Claude”。
8. **不能**把 pane 里旧的 `●`、`REVIEW_WRITTEN`、历史 working 残留当作这次新提交成功。
9. 如果 pane 里同时出现“旧 working 残留 + 当前 prompt 回显”，只允许检查**最后一段 prompt 回显之后**的新输出；回显前的旧 `✻`、`●`、`REVIEW_WRITTEN` 一律不算这次成功。
10. 如果发送前 pane 正停在空闲提示符 `❯`，且 prompt 里可能残留旧草稿，脚本应先发一次 `C-u` 清掉旧输入，再发送新消息。
11. 如果当前消息仍然停留在 pane 底部的 prompt 回显里，而回显之后没有新的实质输出（只有旧残留、UI 文本、或又回到 `❯`），必须判定为**未成功提交**。
12. 如果 pane 处于类似 `bypass permissions on` 这类特殊 UI 状态，只有在**显式 Enter 提交后**看到新的 working 痕迹或当前消息离开 prompt，才算成功；权限 UI 本身不算成功证据。
13. 旧的 working 残留只能作为历史参考，不能作为这一次提交成功的证据。必须看到“**本次消息回显之后**”的新动作。

## 推荐做法

优先使用附带脚本：

```bash
python3 skills/collaboration/claude-tmux-submit-verify/scripts/send_and_verify.py \
  --target agent_claude:0.0 \
  --ensure-target \
  --message '请先读 /data/.../CLAUDE_REVIEW_CURRENT.md，然后按 1/2/3 三点复审。'
```

如果当前不存在 Claude tmux，可以先单独执行：

```bash
python3 skills/collaboration/claude-tmux-submit-verify/scripts/ensure_claude_tmux.py \
  --target agent_claude:0.0
```

在交互终端中，这个脚本会询问你想创建成什么 tmux 会话名；如果你已经知道名字，也可以直接传：

```bash
python3 skills/collaboration/claude-tmux-submit-verify/scripts/ensure_claude_tmux.py \
  --target my_claude:0.0 \
  --session-name my_claude
```

如果上层 workflow 是代码复审，请先由上层脚本或人工发送：

```bash
sudo -n tmux send-keys -t agent_claude:0.0 C-u '/resume <configured-session>' C-m
```

确认会话恢复后，再用本脚本发送真正的 review 请求。

## 成功标准

脚本返回 `0`，并打印类似：

```json
{
  "submitted": true,
  "working_confirmed": true,
  "target": "agent_claude:0.0",
  "attempts": 1
}
```

只有这时，才允许在对外回复里说：

- “我已经发给 Claude 了”
- “Claude 已收到”
- “我已提交审查请求”

注意：这只表示**提交成功**，不表示 Claude 已经完成思考或已经写完 `RESPONSE.md`。提交成功后应进入等待阶段，而不是立刻追加第二条催促消息。

## 失败标准

以下情况都算失败：

- `tmux` 目标会话不存在
- pane 一直停留在 `❯` 提示符
- 当前消息仍停在底部 prompt 回显里，回显后没有新的实质输出
- 发出消息后没有任何新的 working 迹象
- 只看到了消息文本回显，没有看到 Claude 开始处理
- review 任务里没有先恢复用户指定的 Claude session

失败时只能汇报：

- “消息已尝试发送，但还未确认 Claude 进入 working”
- “当前不能证明已经成功提交给 Claude”

## 手动兜底

如果脚本不可用，手动流程也必须满足同一标准：

1. `sudo -n tmux load-buffer -b <buf> -`
2. `sudo -n tmux paste-buffer -d -t agent_claude:0.0 -b <buf>`
3. `sudo -n tmux send-keys -t agent_claude:0.0 C-m`
4. `sudo -n tmux capture-pane -pt agent_claude:0.0 -S -60`
5. 检查是否出现 working 迹象
6. 没有就再补一次 `C-m`
7. 再 capture 一次
8. 仍没有 working，就按失败处理

## 备注

- 这个 skill 只约束“提交是否成功”，不保证 Claude 一定会给出高质量结论。
- 对 review 任务，先恢复“用户指定的 Claude session”是工作流的一部分；本 skill 负责“提交成功校验”，不是替代复审上层编排。
- `claude-review-loop` 和 `codex-claude-shared-research` 在显式走 tmux 路径时都应复用本 skill，而不是各自重新发 tmux 消息。
- 如果要复审具体内容，应把待审路径和检查项写进消息里，不要只发“看看这个”。
- 提交成功后，后续等待/催促纪律应遵循 `claude-review-loop` 里的“等待纪律”，默认先长等，再看落盘，再决定是否温和提醒。
