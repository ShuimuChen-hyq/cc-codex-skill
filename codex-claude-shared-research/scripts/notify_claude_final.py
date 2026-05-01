#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import shlex
import shutil
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
COLLAB_ROOT = SKILL_DIR.parent
DEFAULT_BASE = Path.cwd() / "joint_research"
VERIFY_SCRIPT = COLLAB_ROOT / "claude-tmux-submit-verify" / "scripts" / "send_and_verify.py"
ENSURE_SCRIPT = COLLAB_ROOT / "claude-tmux-submit-verify" / "scripts" / "ensure_claude_tmux.py"
SESSION_CONFIG_PATH = Path.home() / ".codex_claude_skill_session.json"


def default_claude_binary() -> str:
    forced = os.environ.get("HERMES_COLLAB_CLAUDE_BIN", "").strip()
    if forced:
        return forced
    for candidate in ("claude-csm", "claude"):
        if shutil.which(candidate):
            return candidate
    return "claude"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify Claude that Codex final conclusion has been written.")
    parser.add_argument("--task-id", required=True, help="Task id / shared research directory name.")
    parser.add_argument(
        "--target",
        default="agent_claude:0.0",
        help="tmux target pane, default: agent_claude:0.0",
    )
    parser.add_argument(
        "--resume-session",
        default="",
        help="Claude session name to resume first. If omitted, reuse the locally configured default session.",
    )
    parser.add_argument(
        "--mode",
        choices=("noninteractive", "tmux-first"),
        default="noninteractive",
        help="Submission mode. Default: noninteractive",
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
        default=str(Path.cwd()),
        help="Working directory for a newly created Claude tmux session.",
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


def fallback_noninteractive(resume_session: str, message: str) -> subprocess.CompletedProcess[str]:
    parts = [
        default_claude_binary(),
        "--dangerously-skip-permissions",
        "-p",
        "--resume",
        resume_session,
        message,
    ]
    cmd = " ".join(shlex.quote(part) for part in parts)
    return subprocess.run(
        ["su", "-", "csm", "-c", cmd],
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
    cmd = [sys.executable, str(ENSURE_SCRIPT), "--target", args.target, "--cwd", args.cwd]
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
    args = parse_args()
    resume_session = resolve_resume_session(args)
    task_dir = Path(args.base_dir).resolve() / args.task_id
    doc_path = task_dir / "JOINT_RESEARCH.md"
    if not doc_path.exists():
        raise SystemExit(f"Missing shared research doc: {doc_path}")
    if not VERIFY_SCRIPT.exists():
        raise SystemExit(f"Missing verify script: {VERIFY_SCRIPT}")

    message = (
        f"Codex 已经在 {doc_path} 写完 `## Codex Final Conclusion`。"
        "请读取同一文档的最新版本，确认最终结论已落盘。"
        "如无新的阻塞问题，请在 pane 回复一句 FINAL_CONCLUSION_ACK。"
    )
    if args.mode == "noninteractive":
        proc = fallback_noninteractive(resume_session, message)
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

    cmd = [sys.executable, str(VERIFY_SCRIPT), "--target", args.target, "--message", message]
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
