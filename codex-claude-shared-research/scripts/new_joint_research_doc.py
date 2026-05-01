#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_BASE = Path.cwd() / "joint_research"
SESSION_CONFIG_PATH = Path.home() / ".codex_claude_skill_session.json"


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "_", text)
    return text.strip("_") or "task"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a shared Codex-Claude joint research document.")
    parser.add_argument("--task-id", required=True, help="Stable task id, used as directory name.")
    parser.add_argument("--summary", default="", help="Short task summary.")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE), help="Base output directory.")
    parser.add_argument("--claude-target", default="agent_claude:0.0", help="Preferred Claude tmux target.")
    parser.add_argument("--resume-session", default="", help="Claude session name to reuse for noninteractive handoff.")
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
    task_dir = Path(args.base_dir).resolve() / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    doc_path = task_dir / "JOINT_RESEARCH.md"
    manifest_path = task_dir / "manifest.json"

    if not doc_path.exists():
        doc_path.write_text(
            "\n".join(
                [
                    f"# Joint Research: {task_id}",
                    "",
                    f"- task_id: `{task_id}`",
                    f"- summary: `{args.summary or 'TODO'}`",
                    f"- doc_path: `{doc_path}`",
                    "- final_owner: `codex`",
                    f"- claude_target: `{args.claude_target}`",
                    f"- claude_resume_session: `{resume_session}`",
                    "",
                    "## Research Question",
                    "",
                    "- ",
                    "",
                    "## Constraints",
                    "",
                    "- ",
                    "",
                    "## Codex Research",
                    "",
                    "- ",
                    "",
                    "## Claude Research",
                    "",
                    "- pending",
                    "",
                    "## Claude Summary",
                    "",
                    "- pending",
                    "",
                    "## Joint Review",
                    "",
                    "- pending",
                    "",
                    "## Open Questions",
                    "",
                    "- ",
                    "",
                    "## Codex Final Conclusion",
                    "",
                    "- pending",
                    "",
                    "## Claude Notification",
                    "",
                    "- status: `pending`",
                    "- note: ",
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    manifest = {
        "task_id": task_id,
        "summary": args.summary,
        "task_dir": str(task_dir),
        "doc_path": str(doc_path),
        "claude_target": args.claude_target,
        "resume_session": resume_session,
        "final_owner": "codex",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
