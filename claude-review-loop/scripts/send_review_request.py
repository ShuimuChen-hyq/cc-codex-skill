#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
COLLAB_ROOT = SKILL_DIR.parent
DEFAULT_BASE = Path.cwd() / "review_packets"
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
    parser = argparse.ArgumentParser(description="Send a review request to Claude and verify it was truly submitted.")
    parser.add_argument("--task-id", required=True, help="Task id / packet dir name.")
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
        "--skip-resume",
        action="store_true",
        help="Do not resume the Claude session before the review request.",
    )
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE), help="Base directory of review packets.")
    parser.add_argument("--extra-enter-once", action="store_true", help="Forwarded to send_and_verify.py")
    parser.add_argument(
        "--mode",
        choices=("noninteractive", "tmux-first"),
        default="noninteractive",
        help="Submission mode. Default: noninteractive",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not fallback to non-interactive Claude when tmux submit fails (only relevant with --mode tmux-first).",
    )
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


def send_raw_tmux(target: str, message: str) -> None:
    buf = f"claude-review-{uuid.uuid4().hex[:12]}"
    try:
        proc = subprocess.run(
            ["sudo", "-n", "tmux", "send-keys", "-t", target, "C-u"],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux clear-line failed for target={target}")
        time.sleep(0.08)
        proc = subprocess.run(
            ["sudo", "-n", "tmux", "load-buffer", "-b", buf, "-"],
            input=message,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux load-buffer failed for target={target}")
        proc = subprocess.run(
            ["sudo", "-n", "tmux", "paste-buffer", "-d", "-t", target, "-b", buf],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux paste-buffer failed for target={target}")
        time.sleep(0.08)
        proc = subprocess.run(
            ["sudo", "-n", "tmux", "send-keys", "-t", target, "C-m"],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"tmux Enter failed for target={target}")
    finally:
        subprocess.run(
            ["sudo", "-n", "tmux", "delete-buffer", "-b", buf],
            text=True,
            capture_output=True,
        )


def fallback_noninteractive(resume_session: str | None, message: str) -> subprocess.CompletedProcess[str]:
    parts = [
        default_claude_binary(),
        "--dangerously-skip-permissions",
        "-p",
    ]
    if resume_session:
        parts.extend(["--resume", resume_session])
    parts.append(message)
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
    resume_session = "" if args.skip_resume else resolve_resume_session(args)
    packet_dir = Path(args.base_dir).resolve() / args.task_id
    request_md = packet_dir / "REQUEST.md"
    response_md = packet_dir / "RESPONSE.md"
    if not request_md.exists():
        raise SystemExit(f"Missing request file: {request_md}")
    if not response_md.exists():
        raise SystemExit(f"Missing response file: {response_md}")
    if not VERIFY_SCRIPT.exists():
        raise SystemExit(f"Missing verify script: {VERIFY_SCRIPT}")

    message = (
        f"请先读 {request_md} 。"
        f"然后把完整复审结论写回 {response_md} 。"
        "请至少写 review_status、findings、required_changes、residual_risks、final_verdict。"
    )

    if args.mode == "noninteractive":
        fb = fallback_noninteractive(None if args.skip_resume else resume_session, message)
        result = {
            "submitted": fb.returncode == 0,
            "working_confirmed": fb.returncode == 0,
            "mode": "noninteractive",
            "target": args.target,
            "resume_session": None if args.skip_resume else resume_session,
            "reason": "direct_noninteractive_submit",
        }
        if fb.stdout:
            result["stdout_tail"] = fb.stdout.strip()[-500:]
        if fb.stderr:
            result["stderr_tail"] = fb.stderr.strip()[-500:]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if fb.returncode == 0 else 1

    if args.ensure_target or args.mode == "tmux-first":
        try:
            args.target = ensure_target(args)
        except Exception as exc:
            if args.no_fallback:
                print(
                    json.dumps(
                        {
                            "submitted": False,
                            "working_confirmed": False,
                            "target": args.target,
                            "resume_session": resume_session,
                            "reason": "ensure_target_failed",
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 1
            fb = fallback_noninteractive(None if args.skip_resume else resume_session, message)
            result = {
                "submitted": fb.returncode == 0,
                "working_confirmed": fb.returncode == 0,
                "mode": "noninteractive_fallback",
                "target": args.target,
                "resume_session": resume_session,
                "reason": "ensure_target_failed_tmux_fallback_used",
                "error": str(exc),
            }
            if fb.stdout:
                result["stdout_tail"] = fb.stdout.strip()[-500:]
            if fb.stderr:
                result["stderr_tail"] = fb.stderr.strip()[-500:]
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if fb.returncode == 0 else 1

    if not args.skip_resume:
        resume_cmd = f"/resume {resume_session}".strip()
        try:
            send_raw_tmux(args.target, resume_cmd)
            time.sleep(1.0)
        except Exception as exc:
            if args.no_fallback:
                print(
                    json.dumps(
                        {
                            "submitted": False,
                            "working_confirmed": False,
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
            fb = fallback_noninteractive(None if args.skip_resume else resume_session, message)
            result = {
                "submitted": fb.returncode == 0,
                "working_confirmed": fb.returncode == 0,
                "mode": "noninteractive_fallback",
                "target": args.target,
                "resume_session": resume_session,
                "reason": "resume_failed_tmux_fallback_used",
                "error": str(exc),
            }
            if fb.stdout:
                result["stdout_tail"] = fb.stdout.strip()[-500:]
            if fb.stderr:
                result["stderr_tail"] = fb.stderr.strip()[-500:]
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if fb.returncode == 0 else 1

    tmux_message = message + "写完后再在 pane 里回复一句 REVIEW_WRITTEN。"
    cmd = [sys.executable, str(VERIFY_SCRIPT), "--target", args.target, "--message", tmux_message]
    if args.extra_enter_once:
        cmd.append("--extra-enter-once")

    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode == 0 or args.no_fallback:
        return proc.returncode

    fb = fallback_noninteractive(None if args.skip_resume else resume_session, message)
    result = {
        "submitted": fb.returncode == 0,
        "working_confirmed": fb.returncode == 0,
        "mode": "noninteractive_fallback",
        "target": args.target,
        "resume_session": resume_session,
        "reason": "tmux_submit_failed_fallback_used",
    }
    if proc.stdout:
        result["tmux_result"] = proc.stdout.strip()
    if fb.stdout:
        result["stdout_tail"] = fb.stdout.strip()[-500:]
    if fb.stderr:
        result["stderr_tail"] = fb.stderr.strip()[-500:]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if fb.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
