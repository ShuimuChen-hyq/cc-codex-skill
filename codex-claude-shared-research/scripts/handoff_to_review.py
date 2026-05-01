#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
COLLAB_ROOT = SKILL_DIR.parent
JOINT_BASE = Path.cwd() / "joint_research"
REVIEW_BASE = Path.cwd() / "review_packets"
NEW_PACKET = COLLAB_ROOT / "claude-review-loop" / "scripts" / "new_review_packet.py"
SEND_REVIEW = COLLAB_ROOT / "claude-review-loop" / "scripts" / "send_review_request.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Handoff a joint research document into the formal Claude review loop.")
    parser.add_argument("--task-id", required=True, help="Joint research task id.")
    parser.add_argument("--review-task-id", default="", help="Review packet task id. Defaults to <task-id>_final_review.")
    parser.add_argument("--joint-base-dir", default=str(JOINT_BASE), help="Base directory of joint research docs.")
    parser.add_argument("--review-base-dir", default=str(REVIEW_BASE), help="Base directory for review packets.")
    parser.add_argument("--summary", default="", help="Optional summary override for the review packet.")
    parser.add_argument(
        "--send",
        action="store_true",
        help="After creating/updating the review packet, also submit it to Claude via claude-review-loop.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_dir = Path(args.joint_base_dir).resolve() / args.task_id
    doc_path = task_dir / "JOINT_RESEARCH.md"
    if not doc_path.exists():
        raise SystemExit(f"Missing shared research doc: {doc_path}")

    review_task_id = args.review_task_id or f"{args.task_id}_final_review"
    summary = args.summary or f"Final review for joint research document: {args.task_id}"

    proc = subprocess.run(
        [
            sys.executable,
            str(NEW_PACKET),
            "--task-id",
            review_task_id,
            "--summary",
            summary,
            "--base-dir",
            str(Path(args.review_base_dir).resolve()),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    manifest = json.loads(proc.stdout)
    request_md = Path(manifest["request_md"])
    response_md = Path(manifest["response_md"])

    request_md.write_text(
        "\n".join(
            [
                f"# Review Request: {review_task_id}",
                "",
                f"- task_id: `{review_task_id}`",
                f"- summary: `{summary}`",
                f"- joint_research_doc: `{doc_path}`",
                f"- request_path: `{request_md}`",
                f"- response_path: `{response_md}`",
                "",
                "## Context",
                "",
                f"- Current task: formally review joint research document `{doc_path.name}`",
                "- Goal: check document structure, evidence chain, conclusion convergence, and residual risks.",
                "- Scope: use the shared document as the only source of truth; do not create a parallel document.",
                "",
                "## Code Changes",
                "",
                "- Changed files: the joint research document itself",
                "- Key change: Codex has written the final conclusion and now requests formal Claude review.",
                "",
                "## Validation",
                "",
                "- Validation performed: document exists on disk; Claude has contributed `Claude Research / Claude Summary / Joint Review`.",
                "- Result: waiting for Claude to review final conclusion consistency.",
                "",
                "## Review Focus",
                "",
                "- Please focus on whether the evidence supports the final conclusion and whether major gaps or contradictions remain.",
                "- Most likely regression points: inconsistent conclusions across sections or open questions not carried forward correctly.",
                "",
                "## Open Risks",
                "",
                "- If the document needs revision, state which section should change and why.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = {
        "joint_doc": str(doc_path),
        "review_task_id": review_task_id,
        "request_md": str(request_md),
        "response_md": str(response_md),
        "submitted": False,
    }
    if args.send:
        submit = subprocess.run(
            [
                sys.executable,
                str(SEND_REVIEW),
                "--task-id",
                review_task_id,
                "--base-dir",
                str(Path(args.review_base_dir).resolve()),
            ],
            text=True,
            capture_output=True,
        )
        result["submitted"] = submit.returncode == 0
        if submit.stdout:
            result["submit_stdout"] = submit.stdout.strip()[-1200:]
        if submit.stderr:
            result["submit_stderr"] = submit.stderr.strip()[-1200:]

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
