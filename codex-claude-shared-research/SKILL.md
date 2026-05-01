---
name: codex-claude-shared-research
description: 当需要 Codex 与 Claude 围绕同一个主题做联合调研，并把双方研究、双方阶段性汇总、共同审核、Codex 最终结论全部落到同一份 Markdown 时使用。这个 skill 会把流程固定成：创建共享研究文档，Codex 先写初稿，Claude 在同一文档补充独立调研与阶段性汇总，再共同审核，最后由 Codex 统一收敛最终结论并在写完后通知 Claude。
---

# Codex Claude Shared Research

这个 skill 用于 **Codex + Claude 共用一份研究文档** 的协同调研闭环。  
目标不是两边各写各的结论，而是把：

- Codex 的研究
- Claude 的研究
- Claude 的阶段性汇总
- 双方共同审核
- Codex 的最终结论

全部固定到 **同一份 Markdown** 中。

默认 Claude 会话名不再写死。第一次使用这条 skill 时，应先让用户自己指定一个 Claude session 名称，并保存为后续默认值。当前我们本地默认已登记为 `code-review-automation`，但对其他用户不应假定这个名字一定存在。

## 何时使用

- 需要两个 agent 围绕同一个问题联合调研。
- 希望双方共写同一份研究文档，而不是各自散落在 pane 回复里。
- 希望 Claude 不只是回复一句意见，而是要参与独立调研、给出自己的阶段性汇总，再进入共同审核。
- 希望最终结论仍由 Codex 收口。
- 希望 Codex 在写完最终结论后，再主动通知 Claude。

## 固定流程

1. 创建一个共享研究目录和一份共享文档。
2. Codex 先写：
   - 研究问题
   - 已知约束
   - 初步证据
   - 自己的调研笔记
3. 默认通过**非交互 + 完全权限 + resume 会话**给 Claude 发消息：
   - 让他读取这份共享文档
   - 在同一文档中补充 `Claude Research`
   - 在同一文档中补充 `Claude Summary`
   - 在同一文档中补充 `Joint Review`
4. 只有在用户明确要求可视化交互时，才改走 `agent_claude:0.0` 的 tmux 路径。
   - 如果目标 Claude pane 不存在，先通过 `claude-tmux-submit-verify` 的 `ensure_claude_tmux.py` 创建新 tmux
   - 在交互终端里，先询问用户想用什么 tmux 会话名
5. 如果显式使用 tmux 路径，必须确认 Claude 真正进入 working，而不是消息停在提示符。
6. Claude 写完后，Codex 重新读取同一文档。
7. Codex 统一整理冲突、残余不确定性，并写入 `Codex Final Conclusion`。
8. Codex 完成最终结论后，必须再通知 Claude：
   - 最终结论已写完
   - 让 Claude 知道最新版本已经落盘
9. 如果这份共享文档已经进入“正式定稿/批准”阶段，默认再触发一次 `claude-review-loop`，把同一份文档 handoff 到正式复审 packet。

## 默认路径

默认所有共享研究文档写到：

```text
joint_research/<task_id>/
  JOINT_RESEARCH.md
  manifest.json
```

## 文档结构要求

共享文档至少包含这些部分：

- `Research Question`
- `Constraints`
- `Codex Research`
- `Claude Research`
- `Claude Summary`
- `Joint Review`
- `Open Questions`
- `Codex Final Conclusion`
- `Claude Notification`

最终结论必须由 Codex 写在同一份文档的 `Codex Final Conclusion` 小节中。

## 推荐脚本

### 1. 创建共享研究文档

```bash
python3 skills/collaboration/codex-claude-shared-research/scripts/new_joint_research_doc.py \
  --task-id winclip_threshold_investigation \
  --summary 'WinCLIP 阈值策略联合调研'
```

### 2. 通知 Claude 补充研究并共同审核

```bash
python3 skills/collaboration/codex-claude-shared-research/scripts/send_joint_research_request.py \
  --task-id winclip_threshold_investigation
```

默认会把消息发到 `agent_claude:0.0`，并复用已有的 `claude-tmux-submit-verify` 去确认真提交成功。  
如果你显式要求 tmux 路径且 Claude pane 不存在，应先创建新 tmux：

```bash
python3 skills/collaboration/claude-tmux-submit-verify/scripts/ensure_claude_tmux.py \
  --target agent_claude:0.0
```
默认提交方式现已改为：

- **非交互**
- **完全权限**
- **`--resume <configured-session>`**

也就是优先使用：

```bash
su - csm -c 'claude-csm --dangerously-skip-permissions -p --resume <configured-session> "..."'
```

只有你显式指定 `--mode tmux-first` 时，才改走 `agent_claude:0.0` 的可视化提交。

Claude 这一步的要求不是简单 review，而是：

- 做一轮独立调研
- 把证据和观点写进 `Claude Research`
- 给出自己的阶段性汇总，写进 `Claude Summary`
- 再把共同审核意见写进 `Joint Review`

### 3. Codex 写完最终结论后通知 Claude

```bash
python3 skills/collaboration/codex-claude-shared-research/scripts/notify_claude_final.py \
  --task-id winclip_threshold_investigation
```

默认也走：

- **非交互**
- **完全权限**
- **`--resume <configured-session>`**

只有明确要求可视化时才切到 tmux。

### 4. 如需正式批准，再 handoff 到 review loop

```bash
python3 skills/collaboration/codex-claude-shared-research/scripts/handoff_to_review.py \
  --task-id winclip_threshold_investigation \
  --send
```

这一步会：

- 为当前 `JOINT_RESEARCH.md` 创建一个正式 `REQUEST.md / RESPONSE.md` review packet
- 然后触发 `claude-review-loop`
- 让 Claude 对同一份联合文档做最终复审

## 通过标准

只有同时满足下面几点，才算一轮联合调研完成：

1. `JOINT_RESEARCH.md` 已创建并写入初始问题与约束。
2. Codex 已写入自己的研究部分。
3. Claude 已在同一文档中写入 `Claude Research`、`Claude Summary` 与 `Joint Review`。
4. Codex 已写入 `Codex Final Conclusion`。
5. Claude 已收到“最终结论已落盘”的通知。

## 失败标准

以下任何一种都算失败：

- 只在 pane 中讨论，没有把结果写进共享文档
- 非交互命令失败，或没有成功恢复 `code-review-automation`
- 非交互命令失败，或没有成功恢复用户指定的 Claude session
- 如果显式用了 tmux 路径，Claude 没进入 working，就假设他已收到请求
- Claude 只回复一句话，没有在文档中补写 `Claude Research` / `Claude Summary` / `Joint Review`
- Codex 没写最终结论
- 写完最终结论后没有通知 Claude

## 工作纪律

- 双方都围绕同一份 `JOINT_RESEARCH.md` 工作，不要拆成多份零散文档。
- Claude 的职责是独立补充研究、写自己的阶段性汇总、参与共同审核，不是代替 Codex 输出最终结论。
- 最终结论只能由 Codex 在文档中收口。
- Claude 收到最终通知后，如果发现结论仍有问题，应在下一轮继续围绕同一文档修订。
- 第一次使用时先让用户指定 Claude session 名称，并用 `--resume-session <name> --persist-session` 保存。
- 联合调研默认也先恢复用户指定的 Claude session，不要再直接往未知 tmux 上下文里塞长消息。
- 默认优先用非交互完全权限路径；只有你明确要可视化观察时，才走 tmux-first。
- 这条 skill 应主动复用另外两条 skill：
  - tmux 提交/创建 Claude pane 时复用 `claude-tmux-submit-verify`
  - 正式定稿复审时复用 `claude-review-loop`
