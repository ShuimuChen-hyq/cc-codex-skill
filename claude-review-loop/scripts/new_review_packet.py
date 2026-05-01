#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_BASE = Path.cwd() / "review_packets"
SESSION_CONFIG_PATH = Path.home() / ".codex_claude_skill_session.json"


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "_", text)
    return text.strip("_") or "task"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a dedicated REQUEST.md / RESPONSE.md review packet.")
    parser.add_argument("--task-id", required=True, help="Stable task id, used as packet directory name.")
    parser.add_argument("--summary", default="", help="Short task summary.")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE), help="Base output directory for review packets.")
    parser.add_argument("--claude-target", default="agent_claude:0.0", help="Preferred Claude tmux target.")
    parser.add_argument("--resume-session", default="", help="Claude session name to resume.")
    return parser.parse_args()


def load_default_resume_session() -> str:
    if not SESSION_CONFIG_PATH.exists():
        return ""
    try:
        payload = json.loads(SESSION_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("default_resume_session") or "").strip()


def main() -> int:
    args = parse_args()
    resume_session = (args.resume_session or "").strip() or load_default_resume_session() or "<unset>"
    task_id = slugify(args.task_id)
    packet_dir = Path(args.base_dir).resolve() / task_id
    packet_dir.mkdir(parents=True, exist_ok=True)

    request_md = packet_dir / "REQUEST.md"
    response_md = packet_dir / "RESPONSE.md"
    manifest_json = packet_dir / "packet.json"

    if not request_md.exists():
        request_md.write_text(
            "\n".join(
                [
                    f"# Review Request: {task_id}",
                    "",
                    f"- task_id: `{task_id}`",
                    f"- summary: `{args.summary or 'TODO'}`",
                    f"- request_path: `{request_md}`",
                    f"- response_path: `{response_md}`",
                    f"- claude_target: `{args.claude_target}`",
                    f"- claude_resume_session: `{resume_session}`",
                    "",
                    "## Context",
                    "",
                    "- 当前任务：",
                    "- 目标：",
                    "- 本轮范围：",
                    "",
                    "## Code Changes",
                    "",
                    "- 改动文件：",
                    "- 关键变更：",
                    "",
                    "## Validation",
                    "",
                    "- 已执行验证：",
                    "- 结果：",
                    "",
                    "## Review Focus",
                    "",
                    "- 请重点检查：",
                    "- 你认为最可能的回归点：",
                    "",
                    "## Open Risks",
                    "",
                    "- ",
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    if not response_md.exists():
        response_md.write_text(
            "\n".join(
                [
                    f"# Review Response: {task_id}",
                    "",
                    f"- task_id: `{task_id}`",
                    "- review_status: `pending`",
                    "",
                    "## Findings",
                    "",
                    "- ",
                    "",
                    "## Required Changes",
                    "",
                    "- ",
                    "",
                    "## Residual Risks",
                    "",
                    "- ",
                    "",
                    "## Final Verdict",
                    "",
                    "- ",
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    manifest = {
        "task_id": task_id,
        "summary": args.summary,
        "packet_dir": str(packet_dir),
        "request_md": str(request_md),
        "response_md": str(response_md),
        "claude_target": args.claude_target,
        "resume_session": resume_session,
    }
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
