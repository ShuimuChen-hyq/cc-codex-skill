#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_TARGET = os.environ.get("CC_COLLAB_DEFAULT_TARGET", "agent_claude:0.0")


def default_cwd() -> str:
    return os.environ.get("CC_COLLAB_DEFAULT_CWD", str(Path.cwd())).strip()


def default_tmux_command() -> str:
    return os.environ.get("CC_COLLAB_TMUX_COMMAND", "tmux").strip() or "tmux"


def default_claude_command() -> str:
    forced = os.environ.get("CC_COLLAB_CLAUDE_TMUX_COMMAND", "").strip()
    if forced:
        return forced
    binary = os.environ.get("CC_COLLAB_CLAUDE_BIN", "claude").strip() or "claude"
    extra_args = os.environ.get("CC_COLLAB_CLAUDE_EXTRA_ARGS", "--dangerously-skip-permissions").strip()
    return " ".join(part for part in (shlex.quote(binary), extra_args) if part)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ensure a Claude tmux target exists; create one if needed."
    )
    parser.add_argument("--target", default=DEFAULT_TARGET, help=f"Preferred tmux target (default: {DEFAULT_TARGET})")
    parser.add_argument("--session-name", default="", help="Explicit tmux session name to create when target is missing.")
    parser.add_argument("--cwd", default=default_cwd(), help="Working directory for the new Claude tmux.")
    parser.add_argument(
        "--tmux-command",
        default=default_tmux_command(),
        help="tmux command prefix. Examples: 'tmux' or 'sudo -u ccuser tmux'.",
    )
    parser.add_argument(
        "--claude-command",
        default=default_claude_command(),
        help="Command to launch inside the new tmux session.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for a session name if the target is missing; use the provided/default name directly.",
    )
    return parser.parse_args()


def tmux_argv(tmux_command: str, args: list[str]) -> list[str]:
    return [*shlex.split(tmux_command), *args]


def run_tmux(tmux_command: str, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tmux_argv(tmux_command, args),
        text=True,
        capture_output=True,
        check=check,
    )


def target_exists(tmux_command: str, target: str) -> bool:
    proc = run_tmux(tmux_command, ["list-panes", "-a", "-F", "#{session_name}:#{window_index}.#{pane_index}"], check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "tmux list-panes failed")
    panes = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    return target in panes


def derive_session_name(target: str) -> str:
    left = target.split(":", 1)[0].strip()
    return left or "agent_claude"


def choose_session_name(args: argparse.Namespace) -> str:
    default_name = args.session_name.strip() or derive_session_name(args.target)
    if args.no_prompt or not sys.stdin.isatty():
        return default_name
    answer = input(f"Claude tmux target was not found. New session name [{default_name}]: ").strip()
    return answer or default_name


def build_launch_command(cwd: str, claude_command: str) -> str:
    return f"cd {shlex.quote(cwd)} && {claude_command}"


def main() -> int:
    args = parse_args()
    if target_exists(args.tmux_command, args.target):
        print(
            json.dumps(
                {
                    "created": False,
                    "target": args.target,
                    "session_name": derive_session_name(args.target),
                    "reason": "target_exists",
                    "tmux_command": args.tmux_command,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    session_name = choose_session_name(args)
    target = f"{session_name}:0.0"
    if not target_exists(args.tmux_command, target):
        launch_command = build_launch_command(args.cwd, args.claude_command)
        proc = run_tmux(args.tmux_command, ["new-session", "-d", "-s", session_name, launch_command], check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux new-session failed for {session_name}")
        time.sleep(0.5)
    if not target_exists(args.tmux_command, target):
        raise RuntimeError(f"Claude tmux target still missing after create: {target}")

    print(
        json.dumps(
            {
                "created": True,
                "target": target,
                "session_name": session_name,
                "reason": "created_new_tmux",
                "tmux_command": args.tmux_command,
                "claude_command": args.claude_command,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
