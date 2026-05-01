---
name: claude-review-loop
description: Use this skill when Codex needs Claude to review a completed coding change and write the review result back to a dedicated Markdown file.
---

# Claude Review Loop

This skill turns a Claude review into a file-backed workflow. Codex writes `REQUEST.md`, submits it to Claude, requires Claude to write `RESPONSE.md`, then reads the response before deciding whether to fix issues or close the task.

The default submission mode is `tmux-first`. The helper sends through a Claude tmux pane, verifies working state, and only uses noninteractive Claude when explicitly requested or when the review helper falls back after tmux failure.

## Runtime Configuration

- `CC_COLLAB_TMUX_COMMAND`: tmux command prefix. Default: `tmux`.
- `CC_COLLAB_DEFAULT_TARGET`: default Claude pane target. Default: `agent_claude:0.0`.
- `CC_COLLAB_CLAUDE_BIN`: Claude executable for noninteractive mode. Default: `claude`.
- `CC_COLLAB_CLAUDE_EXTRA_ARGS`: extra Claude args for noninteractive mode. Default: `--dangerously-skip-permissions`.
- `CC_COLLAB_CLAUDE_USER`: optional OS user for noninteractive Claude. Leave unset to use the current user.
- `CC_COLLAB_CLAUDE_TMUX_COMMAND`: command launched inside a newly created Claude tmux session.

If Codex runs as root but Claude should run as a normal user, start Claude in that normal user's tmux session and set `CC_COLLAB_TMUX_COMMAND='sudo -u <user> tmux'`. Do not hard-code machine-specific users.

## When To Use

- Codex has completed a code change and needs an independent Claude review.
- The review request must include changed files, validation, risks, and review focus.
- Claude's answer must be written to a persistent `RESPONSE.md`, not only discussed in a tmux pane.

## Fixed Workflow

1. Create one review packet for the task.
2. Write the task context, code changes, validation, review focus, and risks into `REQUEST.md`.
3. Submit the request to Claude with `send_review_request.py`.
4. The helper resumes the configured Claude session unless `--skip-resume` is used.
5. The helper sends the request through tmux and verifies working state.
6. Claude writes the result to `RESPONSE.md`.
7. Codex reads `RESPONSE.md`.
8. If Claude reports valid issues, Codex fixes them and starts another review round.
9. If Claude reports no blocking issues, Codex closes the task.

## Review Packet

Create a packet:

```bash
python3 ~/.codex/skills/claude-review-loop/scripts/new_review_packet.py \
  --task-id my_task_review \
  --summary 'Review the latest implementation'
```

Send it:

```bash
python3 ~/.codex/skills/claude-review-loop/scripts/send_review_request.py \
  --task-id my_task_review
```

Strict tmux-only mode:

```bash
python3 ~/.codex/skills/claude-review-loop/scripts/send_review_request.py \
  --task-id my_task_review \
  --no-fallback
```

Explicit noninteractive mode:

```bash
python3 ~/.codex/skills/claude-review-loop/scripts/send_review_request.py \
  --task-id my_task_review \
  --mode noninteractive
```

## `REQUEST.md` Minimum Content

- Current task
- Goal
- Changed files
- Key changes
- Validation performed
- Residual risks
- Review focus

Do not submit an empty "please look at this" request. Claude needs a concrete review scope.

## `RESPONSE.md` Requirements

Claude should write at least:

- `review_status`
- `findings`
- `required_changes`
- `residual_risks`
- `final_verdict`

If Claude writes semantically clear sections such as `Findings`, `Required Changes`, `Residual Risks`, and `Final Verdict`, treat it as acceptable even if the exact field names are not perfect. If the verdict is ambiguous, the review is incomplete.

## Completion Criteria

- The request was submitted through verified tmux, or explicit noninteractive mode returned successfully.
- `RESPONSE.md` was written by Claude.
- Codex has read the response and acted on valid findings.

## Failure Criteria

- The message stayed at the tmux prompt and working state was not confirmed.
- The helper could not resume the configured Claude session.
- Noninteractive mode failed.
- Claude only replied in the pane and did not write `RESPONSE.md`.
- `RESPONSE.md` does not contain a usable verdict.

## Waiting Discipline

After a verified submission, do not immediately send another message. Wait for Claude to work and check whether `RESPONSE.md` has been written. Only send a gentle reminder if enough time has passed, the file is still missing, and the pane appears idle.
