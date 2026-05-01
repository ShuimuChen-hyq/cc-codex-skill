---
name: codex-claude-shared-research
description: Use this skill when Codex and Claude should investigate one topic in the same Markdown document, with Codex writing the final conclusion.
---

# Codex Claude Shared Research

This skill coordinates joint research in one shared Markdown file. Codex writes the initial context and final conclusion. Claude contributes independent research, an interim summary, and a joint review in the same document.

The default submission mode is `tmux-first`, using the same verified tmux submission rules as `claude-tmux-submit-verify`.

## Runtime Configuration

- `CC_COLLAB_TMUX_COMMAND`: tmux command prefix. Default: `tmux`.
- `CC_COLLAB_DEFAULT_TARGET`: default Claude pane target. Default: `agent_claude:0.0`.
- `CC_COLLAB_CLAUDE_BIN`: Claude executable for noninteractive mode. Default: `claude`.
- `CC_COLLAB_CLAUDE_EXTRA_ARGS`: extra Claude args for noninteractive mode. Default: `--dangerously-skip-permissions`.
- `CC_COLLAB_CLAUDE_USER`: optional OS user for noninteractive Claude. Leave unset to use the current user.
- `CC_COLLAB_CLAUDE_TMUX_COMMAND`: command launched inside a newly created Claude tmux session.

## When To Use

- Codex and Claude need to research the same topic.
- Both agents should write into one document instead of producing separate summaries.
- Claude should add evidence and a joint review, but Codex should own the final conclusion.
- Codex should notify Claude after the final conclusion is written.

## Fixed Workflow

1. Create a shared research directory and `JOINT_RESEARCH.md`.
2. Codex writes the research question, constraints, initial evidence, and Codex research.
3. Codex submits the document to Claude.
4. Claude writes `Claude Research`, `Claude Summary`, and `Joint Review` in the same document.
5. Codex reads the updated document.
6. Codex resolves conflicts, carries forward open questions, and writes `Codex Final Conclusion`.
7. Codex notifies Claude that the final conclusion is persisted.
8. If formal approval is needed, hand the document off to `claude-review-loop`.

## Document Layout

The shared document should include:

- `Research Question`
- `Constraints`
- `Codex Research`
- `Claude Research`
- `Claude Summary`
- `Joint Review`
- `Open Questions`
- `Codex Final Conclusion`
- `Claude Notification`

## Commands

Create a shared document:

```bash
python3 ~/.codex/skills/codex-claude-shared-research/scripts/new_joint_research_doc.py \
  --task-id winclip_eval_comparison \
  --summary 'Compare WinCLIP and OPSD heatmap evaluation metrics'
```

Ask Claude to contribute:

```bash
python3 ~/.codex/skills/codex-claude-shared-research/scripts/send_joint_research_request.py \
  --task-id winclip_eval_comparison
```

Notify Claude after Codex writes the final conclusion:

```bash
python3 ~/.codex/skills/codex-claude-shared-research/scripts/notify_claude_final.py \
  --task-id winclip_eval_comparison
```

Handoff to the formal review loop:

```bash
python3 ~/.codex/skills/codex-claude-shared-research/scripts/handoff_to_review.py \
  --task-id winclip_eval_comparison \
  --send
```

## Completion Criteria

- `JOINT_RESEARCH.md` exists and contains the initial context.
- Codex has written its research section.
- Claude has written `Claude Research`, `Claude Summary`, and `Joint Review`.
- Codex has written `Codex Final Conclusion`.
- Claude has been notified that the final conclusion is persisted.

## Failure Criteria

- Research only happens in the pane and not in the shared document.
- tmux submission is not verified.
- Claude does not write the required sections.
- Codex does not write the final conclusion.
- Codex writes a final conclusion but does not notify Claude.

## Discipline

- Keep all research in one `JOINT_RESEARCH.md`.
- Do not create parallel documents unless the user explicitly asks.
- Claude contributes research and review; Codex owns the final conclusion.
- If the shared document becomes a decision artifact, hand it off to `claude-review-loop`.
