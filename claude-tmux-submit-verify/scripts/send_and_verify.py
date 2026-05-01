#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import List


WORKING_PREFIXES = ("●", "⏺", "✻", "✢", "*")
WORKING_SUBSTRINGS = (
    "Bash(",
    "Read(",
    "Write(",
    "Glob",
    "Grep(",
    "LS(",
    "Search(",
    "Task(",
    "Todo",
    "Propagating",
    "Baking",
    "Fiddle-faddling",
    "esc to interrupt",
)
WORKING_EXACT_LINES = ("REVIEW_WRITTEN",)
IGNORED_UI_SUBSTRINGS = (
    "bypass permissions on",
    "shift+tab to cycle",
)
SCRIPT_DIR = Path(__file__).resolve().parent
ENSURE_SCRIPT = SCRIPT_DIR / "ensure_claude_tmux.py"
DEFAULT_TARGET = os.environ.get("CC_COLLAB_DEFAULT_TARGET", "agent_claude:0.0")
TMUX_COMMAND = (
    os.environ.get("CC_COLLAB_TMUX_COMMAND")
    or "tmux"
).strip() or "tmux"


def default_claude_command() -> str:
    forced = os.environ.get("CC_COLLAB_CLAUDE_TMUX_COMMAND", "").strip()
    if forced:
        return forced
    binary = os.environ.get("CC_COLLAB_CLAUDE_BIN", "claude").strip() or "claude"
    extra_args = os.environ.get("CC_COLLAB_CLAUDE_EXTRA_ARGS", "--dangerously-skip-permissions").strip()
    return " ".join(part for part in (shlex.quote(binary), extra_args) if part)


def tmux_argv(args: List[str]) -> List[str]:
    return [*shlex.split(TMUX_COMMAND), *args]


def run_tmux(args: List[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tmux_argv(args),
        text=True,
        capture_output=True,
        check=check,
    )


def tmux_load_and_paste(target: str, message: str, clear_prompt_first: bool = False) -> None:
    buf = f"claude-submit-{uuid.uuid4().hex[:12]}"
    try:
        if clear_prompt_first:
            proc = run_tmux(["send-keys", "-t", target, "C-u"], check=False)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or f"tmux send-keys C-u failed for target={target}")
            time.sleep(0.08)
        proc = subprocess.run(
            tmux_argv(["load-buffer", "-b", buf, "-"]),
            input=message,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux load-buffer failed for target={target}")
        proc = run_tmux(["paste-buffer", "-d", "-t", target, "-b", buf], check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux paste-buffer failed for target={target}")
        time.sleep(0.08)
        proc = run_tmux(["send-keys", "-t", target, "C-m"], check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux send-keys Enter failed for target={target}")
    finally:
        run_tmux(["delete-buffer", "-b", buf], check=False)


def capture(target: str, scrollback: int) -> str:
    proc = run_tmux(["capture-pane", "-pt", target, "-S", f"-{scrollback}"], check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"tmux capture-pane failed for target={target}")
    return proc.stdout


def last_nonempty_line(text: str) -> str:
    for line in reversed(meaningful_lines(text)):
        if line.strip():
            return line.rstrip()
    return ""


def is_ui_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if set(stripped) <= {"─"}:
        return True
    if any(token in stripped for token in IGNORED_UI_SUBSTRINGS):
        return True
    return False


def meaningful_lines(text: str) -> List[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip() and not is_ui_line(line)]


def is_prompt_line(line: str) -> bool:
    return line.lstrip().startswith("❯")


def strip_prompt_prefix(line: str) -> str:
    stripped = line.strip()
    if is_prompt_line(stripped):
        return stripped.lstrip("❯").strip()
    return stripped


def has_working_marker(lines: List[str]) -> bool:
    for line in lines[-40:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in WORKING_EXACT_LINES:
            return True
        if stripped.startswith(WORKING_PREFIXES):
            return True
        if any(token in stripped for token in WORKING_SUBSTRINGS):
            return True
    return False


def substantive_post_echo_lines(lines: List[str]) -> List[str]:
    """Keep only post-echo lines that represent actual new activity."""
    kept: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if is_prompt_line(stripped):
            continue
        kept.append(line.rstrip())
    return kept


def idle_prompt_only(text: str) -> bool:
    line = last_nonempty_line(text).lstrip()
    return line.startswith("❯")


def normalize_compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def extract_new_lines(before: str, after: str) -> List[str]:
    before_lines = meaningful_lines(before)
    after_lines = meaningful_lines(after)
    if not after_lines:
        return []

    prefix = 0
    max_prefix = min(len(before_lines), len(after_lines))
    while prefix < max_prefix and before_lines[prefix] == after_lines[prefix]:
        prefix += 1
    if prefix > 0:
        return after_lines[prefix:]

    max_overlap = min(len(before_lines), len(after_lines))
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if before_lines[-size:] == after_lines[:size]:
            overlap = size
            break
    return after_lines[overlap:]


def delta_is_just_echo(new_lines: List[str], message: str) -> bool:
    payload_lines = []
    for line in new_lines:
        stripped = line.strip()
        if not stripped:
            continue
        stripped = strip_prompt_prefix(stripped)
        payload_lines.append(stripped)
    if not payload_lines:
        return False
    delta = normalize_compact(" ".join(payload_lines))
    msg = normalize_compact(message)
    if not delta or not msg:
        return False
    return delta in msg or msg in delta


def split_after_latest_prompt_echo(new_lines: List[str], message: str) -> tuple[List[str], List[str]]:
    prompt_indexes = [idx for idx, line in enumerate(new_lines) if is_prompt_line(line)]
    if not prompt_indexes:
        return [], new_lines

    msg = normalize_compact(message)
    for last_prompt in reversed(prompt_indexes):
        echo_end = last_prompt - 1
        compact = ""

        for idx in range(last_prompt, len(new_lines)):
            piece = strip_prompt_prefix(new_lines[idx])
            candidate = normalize_compact(f"{compact} {piece}".strip())
            if msg and candidate and msg.startswith(candidate):
                compact = candidate
                echo_end = idx
                continue
            break

        if echo_end >= last_prompt:
            return new_lines[last_prompt : echo_end + 1], new_lines[echo_end + 1 :]

    return [], new_lines


def send_message(target: str, message: str, clear_prompt_first: bool = False) -> None:
    tmux_load_and_paste(target, message, clear_prompt_first=clear_prompt_first)


def verify_working(
    target: str,
    before: str,
    message: str,
    timeout: float,
    poll_interval: float,
    scrollback: int,
) -> dict:
    deadline = time.time() + timeout
    last_text = before
    while time.time() < deadline:
        text = capture(target, scrollback)
        full_lines = meaningful_lines(text)
        full_echo_lines, full_post_echo_lines = split_after_latest_prompt_echo(full_lines, message)
        full_substantive_post_echo = substantive_post_echo_lines(full_post_echo_lines)
        if full_echo_lines and has_working_marker(full_substantive_post_echo):
            return {
                "submitted": True,
                "working_confirmed": True,
                "reason": "working_marker_detected_in_full_pane_after_current_submit",
                "last_nonempty_line": last_nonempty_line(text),
                "post_echo_lines": full_substantive_post_echo[-10:],
            }
        if (
            full_echo_lines
            and full_substantive_post_echo
            and not delta_is_just_echo(full_substantive_post_echo, message)
        ):
            return {
                "submitted": True,
                "working_confirmed": True,
                "reason": "output_detected_in_full_pane_after_current_submit",
                "last_nonempty_line": last_nonempty_line(text),
                "post_echo_lines": full_substantive_post_echo[-10:],
            }

        new_lines = extract_new_lines(before, text)
        changed = bool(new_lines)
        echo_lines, post_echo_lines = split_after_latest_prompt_echo(new_lines, message)
        relevant_lines = substantive_post_echo_lines(post_echo_lines) if echo_lines else []

        if changed and has_working_marker(relevant_lines):
            return {
                "submitted": True,
                "working_confirmed": True,
                "reason": "working_marker_detected_after_current_submit",
                "last_nonempty_line": last_nonempty_line(text),
                "new_lines": new_lines[-10:],
                "post_echo_lines": relevant_lines[-10:],
            }
        if changed and echo_lines and not post_echo_lines:
            last_text = text
            time.sleep(poll_interval)
            continue
        if changed and not echo_lines:
            last_text = text
            time.sleep(poll_interval)
            continue
        if changed and delta_is_just_echo(relevant_lines, message):
            last_text = text
            time.sleep(poll_interval)
            continue
        if changed and relevant_lines and not idle_prompt_only(text):
            return {
                "submitted": True,
                "working_confirmed": True,
                "reason": "post_submit_output_left_idle_prompt",
                "last_nonempty_line": last_nonempty_line(text),
                "new_lines": new_lines[-10:],
                "post_echo_lines": relevant_lines[-10:],
            }
        last_text = text
        time.sleep(poll_interval)
    return {
        "submitted": False,
        "working_confirmed": False,
        "reason": "timeout_without_working_marker",
        "last_nonempty_line": last_nonempty_line(last_text),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a message to Claude via tmux and only succeed if working state is confirmed."
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"tmux target pane, default: {DEFAULT_TARGET}",
    )
    parser.add_argument(
        "--tmux-command",
        default=TMUX_COMMAND,
        help="tmux command prefix. Examples: 'tmux' or 'sudo -u ccuser tmux'.",
    )
    parser.add_argument("--message", required=True, help="Message to send")
    parser.add_argument("--timeout", type=float, default=8.0, help="Seconds to wait per verification attempt")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="Polling interval in seconds")
    parser.add_argument("--scrollback", type=int, default=120, help="capture-pane scrollback depth")
    parser.add_argument(
        "--extra-enter-once",
        action="store_true",
        help="If first attempt does not confirm working, send one extra Enter and verify again.",
    )
    parser.add_argument(
        "--ensure-target",
        action="store_true",
        help="Create/reuse a Claude tmux target first when the requested pane is missing.",
    )
    parser.add_argument(
        "--session-name",
        default="",
        help="Preferred Claude tmux session name when creating a missing target.",
    )
    parser.add_argument(
        "--cwd",
        default=os.environ.get("CC_COLLAB_DEFAULT_CWD", str(Path.cwd())).strip(),
        help="Working directory for a newly created Claude tmux session.",
    )
    parser.add_argument(
        "--claude-command",
        default=default_claude_command(),
        help="Command to launch if a missing Claude tmux target is created.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for session name when creating a missing Claude tmux target.",
    )
    return parser.parse_args()


def ensure_target(args: argparse.Namespace) -> str:
    cmd = [
        sys.executable,
        str(ENSURE_SCRIPT),
        "--target",
        args.target,
        "--cwd",
        args.cwd,
        "--tmux-command",
        args.tmux_command,
        "--claude-command",
        args.claude_command,
    ]
    if args.session_name:
        cmd.extend(["--session-name", args.session_name])
    if args.no_prompt:
        cmd.append("--no-prompt")
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "ensure_claude_tmux failed")
    payload = json.loads(proc.stdout)
    return payload.get("target") or args.target


def main() -> int:
    global TMUX_COMMAND
    args = parse_args()
    TMUX_COMMAND = args.tmux_command
    try:
        if args.ensure_target:
            args.target = ensure_target(args)
        before = capture(args.target, args.scrollback)
        send_message(args.target, args.message, clear_prompt_first=idle_prompt_only(before))
        result = verify_working(
            target=args.target,
            before=before,
            message=args.message,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            scrollback=args.scrollback,
        )
        result["target"] = args.target
        result["attempts"] = 1

        if not result["working_confirmed"] and args.extra_enter_once:
            before_retry = capture(args.target, args.scrollback)
            run_tmux(["send-keys", "-t", args.target, "C-m"], check=False)
            retry = verify_working(
                target=args.target,
                before=before_retry,
                message=args.message,
                timeout=args.timeout,
                poll_interval=args.poll_interval,
                scrollback=args.scrollback,
            )
            retry["target"] = args.target
            retry["attempts"] = 2
            result = retry

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["working_confirmed"] else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "submitted": False,
                    "working_confirmed": False,
                    "target": args.target,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
