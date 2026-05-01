#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import shlex
import time
import uuid
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
COLLAB_ROOT = SKILL_DIR.parent
DEFAULT_BASE = Path.cwd() / "joint_research"
VERIFY_SCRIPT = COLLAB_ROOT / "claude-tmux-submit-verify" / "scripts" / "send_and_verify.py"
ENSURE_SCRIPT = COLLAB_ROOT / "claude-tmux-submit-verify" / "scripts" / "ensure_claude_tmux.py"
SESSION_CONFIG_PATH = Path.home() / ".codex_claude_skill_session.json"
DEFAULT_TARGET = os.environ.get("CC_COLLAB_DEFAULT_TARGET", "agent_claude:0.0")


def default_tmux_command() -> str:
    return os.environ.get("CC_COLLAB_TMUX_COMMAND", "tmux").strip() or "tmux"


def default_claude_binary() -> str:
    return os.environ.get("CC_COLLAB_CLAUDE_BIN", "claude").strip() or "claude"


def default_claude_extra_args() -> str:
    return os.environ.get("CC_COLLAB_CLAUDE_EXTRA_ARGS", "--dangerously-skip-permissions").strip()


def default_claude_user() -> str:
    return os.environ.get("CC_COLLAB_CLAUDE_USER", "").strip()


def default_claude_tmux_command() -> str:
    forced = os.environ.get("CC_COLLAB_CLAUDE_TMUX_COMMAND", "").strip()
    if forced:
        return forced
    return " ".join(
        part for part in (shlex.quote(default_claude_binary()), default_claude_extra_args()) if part
    )


def tmux_argv(tmux_command: str, args: list[str]) -> list[str]:
    return [*shlex.split(tmux_command), *args]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify Claude that Codex final conclusion has been written.")
    parser.add_argument("--task-id", required=True, help="Task id / shared research directory name.")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"tmux target pane, default: {DEFAULT_TARGET}",
    )
    parser.add_argument(
        "--tmux-command",
        default=default_tmux_command(),
        help="tmux command prefix. Examples: 'tmux' or 'sudo -u ccuser tmux'.",
    )
    parser.add_argument(
        "--resume-session",
        default="",
        help="Claude session name to resume first. If omitted, reuse the locally configured default session.",
    )
    parser.add_argument(
        "--mode",
        choices=("noninteractive", "tmux-first"),
        default="tmux-first",
        help="Submission mode. Default: tmux-first. Use --mode noninteractive to bypass tmux.",
    )
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE), help="Base directory of shared research docs.")
    parser.add_argument("--extra-enter-once", action="store_true", help="Forwarded to send_and_verify.py")
    parser.add_argument(
        "--ensure-target",
        action="store_true",
        help="When tmux-first is used, create/reuse a Claude tmux target first if needed.",
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
        default=default_claude_tmux_command(),
        help="Command to launch if a missing Claude tmux target is created.",
    )
    parser.add_argument(
        "--claude-bin",
        default=default_claude_binary(),
        help="Claude executable for noninteractive mode.",
    )
    parser.add_argument(
        "--claude-extra-args",
        default=default_claude_extra_args(),
        help="Extra Claude args for noninteractive mode.",
    )
    parser.add_argument(
        "--claude-user",
        default=default_claude_user(),
        help="Optional OS user for noninteractive Claude. Leave empty to run as the current user.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for tmux session name when creating a missing target.",
    )
    parser.add_argument(
        "--persist-session",
        action="store_true",
        help="Persist the provided --resume-session as the local default for future runs.",
    )
    return parser.parse_args()


def fallback_noninteractive(
    resume_session: str,
    message: str,
    args: argparse.Namespace,
) -> subprocess.CompletedProcess[str]:
    parts = [
        args.claude_bin,
        *shlex.split(args.claude_extra_args),
        "-p",
        "--resume",
        resume_session,
        message,
    ]
    if args.claude_user:
        parts = ["sudo", "-u", args.claude_user, "--", *parts]
    return subprocess.run(
        parts,
        text=True,
        capture_output=True,
    )


def load_default_resume_session() -> str:
    if not SESSION_CONFIG_PATH.exists():
        return ""
    try:
        payload = json.loads(SESSION_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("default_resume_session") or "").strip()


def save_default_resume_session(name: str) -> None:
    SESSION_CONFIG_PATH.write_text(
        json.dumps({"default_resume_session": name}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_resume_session(args: argparse.Namespace) -> str:
    session = (args.resume_session or "").strip()
    if session:
        if args.persist_session:
            save_default_resume_session(session)
        return session
    session = load_default_resume_session()
    if session:
        return session
    raise SystemExit(
        "No Claude session configured. Ask the user to name a Claude session first, then rerun with "
        "--resume-session <name> --persist-session."
    )


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


def send_raw_tmux(target: str, message: str, tmux_command: str) -> None:
    buf = f"joint-final-{uuid.uuid4().hex[:12]}"
    try:
        proc = subprocess.run(
            tmux_argv(tmux_command, ["send-keys", "-t", target, "C-u"]),
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux clear-line failed for target={target}")
        time.sleep(0.08)
        proc = subprocess.run(
            tmux_argv(tmux_command, ["load-buffer", "-b", buf, "-"]),
            input=message,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux load-buffer failed for target={target}")
        proc = subprocess.run(
            tmux_argv(tmux_command, ["paste-buffer", "-d", "-t", target, "-b", buf]),
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux paste-buffer failed for target={target}")
        time.sleep(0.08)
        proc = subprocess.run(
            tmux_argv(tmux_command, ["send-keys", "-t", target, "C-m"]),
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux Enter failed for target={target}")
    finally:
        subprocess.run(
            tmux_argv(tmux_command, ["delete-buffer", "-b", buf]),
            text=True,
            capture_output=True,
        )


def main() -> int:
    args = parse_args()
    resume_session = resolve_resume_session(args)
    task_dir = Path(args.base_dir).resolve() / args.task_id
    doc_path = task_dir / "JOINT_RESEARCH.md"
    if not doc_path.exists():
        raise SystemExit(f"Missing shared research doc: {doc_path}")
    if not VERIFY_SCRIPT.exists():
        raise SystemExit(f"Missing verify script: {VERIFY_SCRIPT}")

    message = (
        f"Codex has written `## Codex Final Conclusion` in {doc_path}. "
        "Please read the latest version of the same document and confirm the final conclusion is persisted. "
        "If there is no new blocking issue, reply in the pane with FINAL_CONCLUSION_ACK."
    )
    if args.mode == "noninteractive":
        proc = fallback_noninteractive(resume_session, message, args)
        result = {
            "submitted": proc.returncode == 0,
            "working_confirmed": proc.returncode == 0,
            "mode": "noninteractive",
            "target": args.target,
            "resume_session": resume_session,
        }
        if proc.stdout:
            result["stdout_tail"] = proc.stdout.strip()[-500:]
        if proc.stderr:
            result["stderr_tail"] = proc.stderr.strip()[-500:]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return proc.returncode

    if args.ensure_target or args.mode == "tmux-first":
        args.target = ensure_target(args)

    try:
        send_raw_tmux(args.target, f"/resume {resume_session}".strip(), args.tmux_command)
        time.sleep(1.0)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "submitted": False,
                    "working_confirmed": False,
                    "mode": "tmux-first",
                    "target": args.target,
                    "resume_session": resume_session,
                    "reason": "resume_failed",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    cmd = [
        sys.executable,
        str(VERIFY_SCRIPT),
        "--target",
        args.target,
        "--tmux-command",
        args.tmux_command,
        "--message",
        message,
    ]
    if args.extra_enter_once:
        cmd.append("--extra-enter-once")

    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
