---
name: claude-tmux-submit-verify
description: Use this skill when Codex must send a message to a Claude Code tmux pane and verify that Claude actually started working after Enter was submitted.
---

# Claude Tmux Submit Verify

This skill handles one invariant: pasting text into a Claude prompt is not enough. A submission is only successful after the message is submitted with Enter and the pane shows new activity for the current message.

The default target is `agent_claude:0.0`, but it is only a convention. Override it with `--target` or `CC_COLLAB_DEFAULT_TARGET`.

## Runtime Configuration

- `CC_COLLAB_TMUX_COMMAND`: tmux command prefix. Default: `tmux`. Use values such as `sudo -u ccuser tmux` when Codex runs as root but Claude runs under a normal user.
- `CC_COLLAB_DEFAULT_TARGET`: default Claude pane target. Default: `agent_claude:0.0`.
- `CC_COLLAB_DEFAULT_CWD`: working directory for newly created Claude tmux sessions.
- `CC_COLLAB_CLAUDE_TMUX_COMMAND`: command launched inside a newly created Claude tmux session. Default: `claude --dangerously-skip-permissions`.
- `CC_COLLAB_CLAUDE_BIN`: Claude executable used to build the default tmux launch command.
- `CC_COLLAB_CLAUDE_EXTRA_ARGS`: extra Claude args used to build the default tmux launch command. Default: `--dangerously-skip-permissions`.

## When To Use

- You need to send review, handoff, or research instructions to Claude through tmux.
- You are about to say that a message was submitted to Claude.
- You suspect the text was pasted at the prompt but not actually submitted.

## Hard Rules

1. Use `load-buffer -> paste-buffer -> send-keys C-m`; do not rely on one large `send-keys` call for long messages.
2. Capture the pane after submission.
3. Treat the submission as successful only if there is new activity after the current message echo.
4. Do not count stale `●`, `REVIEW_WRITTEN`, or historical working output as proof for the current submission.
5. If the message remains at the idle `❯` prompt, the submission is not confirmed.
6. If the first attempt is not confirmed, at most send one extra Enter and verify again.
7. If working state is still not confirmed, report failure; do not claim Claude received the task.

## Recommended Commands

Send and verify:

```bash
python3 ~/.codex/skills/claude-tmux-submit-verify/scripts/send_and_verify.py \
  --target agent_claude:0.0 \
  --message 'Please review /path/to/REQUEST.md and write the result to /path/to/RESPONSE.md.'
```

Create the Claude tmux target if missing:

```bash
python3 ~/.codex/skills/claude-tmux-submit-verify/scripts/ensure_claude_tmux.py \
  --target agent_claude:0.0
```

If Codex runs as root while Claude runs as user `ccuser`:

```bash
export CC_COLLAB_TMUX_COMMAND='sudo -u ccuser tmux'
python3 ~/.codex/skills/claude-tmux-submit-verify/scripts/send_and_verify.py \
  --target agent_claude:0.0 \
  --message 'Please read the request file and start the review.'
```

## Success Criteria

The script returns `0` and prints JSON similar to:

```json
{
  "submitted": true,
  "working_confirmed": true,
  "target": "agent_claude:0.0",
  "attempts": 1
}
```

This means the request was submitted. It does not mean Claude has completed the task or written the requested output file.

## Failure Criteria

- The tmux target does not exist and cannot be created.
- The current message remains at the prompt.
- There is no new working signal after the current message echo.
- Only old pane output suggests activity.
- A review workflow skipped the required `/resume <configured-session>` step.

## Manual Fallback

If the helper script is unavailable, follow the same invariant manually:

1. Load the message into a tmux buffer.
2. Paste it into the target pane.
3. Send Enter explicitly.
4. Capture the pane.
5. Confirm there is new activity after the current message echo.
6. If not confirmed, send one extra Enter and capture again.
7. If still not confirmed, report that submission was not verified.
