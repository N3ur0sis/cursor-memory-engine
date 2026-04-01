#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import select
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
MEMORY_DIR = ROOT_DIR / ".cursor-memory"
SHARED_DIR = MEMORY_DIR / "shared"
LOCAL_DIR = MEMORY_DIR / "local"

KIND_TO_FILE = {
    "decision": SHARED_DIR / "decisions.jsonl",
    "convention": SHARED_DIR / "conventions.jsonl",
    "reference": SHARED_DIR / "references.jsonl",
    "pitfall": SHARED_DIR / "pitfalls.jsonl",
    "workflow": SHARED_DIR / "workflows.jsonl",
    "session": LOCAL_DIR / "session.jsonl",
    "preference": LOCAL_DIR / "user-preferences.jsonl",
}

SECTION_ORDER = [
    "decision",
    "convention",
    "workflow",
    "reference",
    "pitfall",
    "preference",
    "session",
]

SECTION_TITLES = {
    "decision": "Shared Decisions",
    "convention": "Shared Conventions",
    "workflow": "Shared Workflows",
    "reference": "Shared References",
    "pitfall": "Shared Pitfalls",
    "preference": "Local Preferences",
    "session": "Active Session",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def flatten_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            result.extend(flatten_list(value))
            continue
        for part in str(value).split(","):
            cleaned = part.strip()
            if cleaned:
                result.append(cleaned)
    return result


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_key(value: str) -> str:
    return normalize_space(value).lower()


def record_scope(kind: str) -> str:
    if kind in {"session", "preference"}:
        return "local"
    return "shared"


def memory_path(kind: str) -> Path:
    path = KIND_TO_FILE.get(kind)
    if path is None:
        allowed = ", ".join(sorted(KIND_TO_FILE))
        raise SystemExit(f"Unsupported kind '{kind}'. Allowed kinds: {allowed}")
    return path


def ensure_dirs() -> None:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    ensure_dirs()
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    content = "\n".join(json.dumps(record, sort_keys=True, ensure_ascii=True) for record in records)
    tmp_path.write_text(f"{content}\n" if content else "\n", encoding="utf-8")
    os.replace(tmp_path, path)


@contextmanager
def file_lock(path: Path):
    ensure_dirs()
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    handle = lock_path.open("a+", encoding="utf-8")
    start = time.time()

    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.time() - start > 5:
                handle.close()
                raise SystemExit(f"Timed out waiting for lock: {lock_path}")
            time.sleep(0.05)

    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def stable_record_key(record: dict[str, Any]) -> str:
    base = "|".join(
        [
            record.get("kind", ""),
            normalize_key(str(record.get("summary", ""))),
            "|".join(sorted(flatten_list(record.get("files")))),
            "|".join(sorted(flatten_list(record.get("tags")))),
            record.get("scope", record_scope(str(record.get("kind", "")))),
        ]
    )
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"cm-{digest}"


def parse_json_payload(payload: str) -> list[dict[str, Any]]:
    parsed = json.loads(payload)
    if isinstance(parsed, list):
        items = parsed
    else:
        items = [parsed]

    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise SystemExit("Each input record must be a JSON object.")
        records.append(item)
    return records


def read_stdin_if_available() -> str:
    if sys.stdin.isatty():
        return ""
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
    except (OSError, ValueError):
        return ""
    if not ready:
        return ""
    return sys.stdin.read().strip()


def build_capture_record(args: argparse.Namespace) -> dict[str, Any]:
    if not args.kind or not args.summary:
        raise SystemExit("capture requires --kind and --summary when stdin is not provided.")

    record: dict[str, Any] = {
        "kind": args.kind,
        "summary": args.summary,
    }
    if args.details:
        record["details"] = args.details
    if args.files:
        record["files"] = args.files
    if args.tags:
        record["tags"] = args.tags
    if args.status:
        record["status"] = args.status
    if args.expires_at:
        record["expires_at"] = args.expires_at
    if args.source:
        record["source"] = {"note": args.source}
    return record


def build_session_record(args: argparse.Namespace) -> dict[str, Any]:
    summary = args.summary or args.goal
    if not summary:
        raise SystemExit("intake requires --summary or --goal.")

    record: dict[str, Any] = {
        "kind": "session",
        "summary": summary,
        "goal": args.goal or summary,
        "status": args.status or "active",
    }
    if args.details:
        record["details"] = args.details
    if args.files:
        record["files"] = args.files
    if args.constraints:
        record["constraints"] = args.constraints
    if args.choices:
        record["choices"] = args.choices
    if args.acceptance:
        record["acceptance"] = args.acceptance
    if args.open_questions:
        record["open_questions"] = args.open_questions
    if args.tags:
        record["tags"] = args.tags
    record["source"] = {"note": "task packet"}
    return record


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    kind = str(record.get("kind", "")).strip()
    if not kind:
        raise SystemExit("Every record requires a kind.")
    memory_path(kind)

    summary = normalize_space(str(record.get("summary", "") or record.get("goal", "")))
    if not summary:
        raise SystemExit(f"{kind} records require a non-empty summary.")

    scope = record_scope(kind)
    explicit_scope = str(record.get("scope", scope)).strip() or scope
    if explicit_scope != scope:
        raise SystemExit(f"{kind} records must use scope '{scope}'.")

    normalized: dict[str, Any] = {
        "kind": kind,
        "scope": scope,
        "summary": summary,
        "status": str(record.get("status", "active")).strip() or "active",
        "files": flatten_list(record.get("files")),
        "tags": flatten_list(record.get("tags")),
        "recorded_at": str(record.get("recorded_at", utc_now())),
        "updated_at": utc_now(),
    }

    details = normalize_space(str(record.get("details", "")))
    if details:
        normalized["details"] = details

    if "goal" in record:
        normalized["goal"] = normalize_space(str(record.get("goal", "")))
    if "constraints" in record:
        normalized["constraints"] = flatten_list(record.get("constraints"))
    if "choices" in record:
        normalized["choices"] = flatten_list(record.get("choices"))
    if "acceptance" in record:
        normalized["acceptance"] = flatten_list(record.get("acceptance"))
    if "open_questions" in record:
        normalized["open_questions"] = flatten_list(record.get("open_questions"))
    if "expires_at" in record and record.get("expires_at"):
        normalized["expires_at"] = str(record["expires_at"])
    if "source" in record and record.get("source"):
        normalized["source"] = record["source"]
    if "supersedes" in record and record.get("supersedes"):
        normalized["supersedes"] = flatten_list(record.get("supersedes"))

    for key, value in record.items():
        if key in normalized or key in {"id", "scope"}:
            continue
        if key in {"kind", "summary", "details", "files", "tags", "status", "recorded_at", "updated_at"}:
            continue
        if key in {"goal", "constraints", "choices", "acceptance", "open_questions", "expires_at", "source", "supersedes"}:
            continue
        normalized[key] = value

    normalized["id"] = str(record.get("id") or stable_record_key(normalized))
    return normalized


def upsert_records(records: list[dict[str, Any]]) -> tuple[int, int]:
    by_path: dict[Path, list[dict[str, Any]]] = {}
    for record in records:
        path = memory_path(record["kind"])
        by_path.setdefault(path, []).append(record)

    created = 0
    updated = 0

    for path, path_records in by_path.items():
        with file_lock(path):
            existing = load_jsonl(path)
            id_index = {str(item.get("id")): index for index, item in enumerate(existing) if item.get("id")}
            key_index = {stable_record_key(item): index for index, item in enumerate(existing)}

            for record in path_records:
                index = id_index.get(record["id"])
                if index is None:
                    index = key_index.get(stable_record_key(record))

                if index is None:
                    existing.append(record)
                    id_index[record["id"]] = len(existing) - 1
                    key_index[stable_record_key(record)] = len(existing) - 1
                    created += 1
                    continue

                previous = existing[index]
                merged = dict(previous)
                merged.update(record)
                merged["id"] = str(previous.get("id") or record["id"])
                merged["recorded_at"] = str(previous.get("recorded_at", record["recorded_at"]))
                merged["updated_at"] = record["updated_at"]
                existing[index] = merged
                updated += 1

            write_jsonl(path, existing)

    return created, updated


def parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_expired(record: dict[str, Any]) -> bool:
    expires_at = parse_iso_date(str(record.get("expires_at", "")))
    if expires_at is None:
        return False
    return expires_at < datetime.now(timezone.utc)


def matches_file(record_file: str, requested_file: str) -> bool:
    left = record_file.strip()
    right = requested_file.strip()
    return left == right or left.endswith(right) or right.endswith(left)


def query_terms(query: str | None) -> list[str]:
    if not query:
        return []
    return [term for term in re.split(r"[^a-zA-Z0-9_]+", query.lower()) if len(term) > 1]


def recall_records(files: list[str], tags: list[str], query: str | None, limit: int) -> list[dict[str, Any]]:
    requested_files = flatten_list(files)
    requested_tags = {tag.lower() for tag in flatten_list(tags)}
    terms = query_terms(query)

    records: list[dict[str, Any]] = []
    for path in dict.fromkeys(KIND_TO_FILE.values()):
        records.extend(load_jsonl(path))

    scored: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") not in {None, "", "active"}:
            continue
        if is_expired(record):
            continue

        score = 1

        record_files = flatten_list(record.get("files"))
        matched_files = [needle for needle in requested_files if any(matches_file(path, needle) for path in record_files)]
        if matched_files:
            score += 50 + (10 * (len(matched_files) - 1))

        record_tags = {tag.lower() for tag in flatten_list(record.get("tags"))}
        tag_hits = requested_tags & record_tags
        score += 20 * len(tag_hits)

        haystack = " ".join(
            [
                str(record.get("summary", "")),
                str(record.get("details", "")),
                " ".join(record_files),
                " ".join(record_tags),
                " ".join(flatten_list(record.get("constraints"))),
                " ".join(flatten_list(record.get("choices"))),
                " ".join(flatten_list(record.get("acceptance"))),
                " ".join(flatten_list(record.get("open_questions"))),
            ]
        ).lower()

        for term in terms:
            if term in haystack:
                score += 6

        updated_at = parse_iso_date(str(record.get("updated_at", "")))
        if updated_at is not None:
            age_days = (datetime.now(timezone.utc) - updated_at).days
            if age_days <= 7:
                score += 4
            elif age_days <= 30:
                score += 2

        if record.get("kind") == "session":
            score += 15
        elif record.get("scope") == "local":
            score += 5

        if requested_files or requested_tags or terms:
            if score == 1:
                continue

        enriched = dict(record)
        enriched["_score"] = score
        scored.append(enriched)

    scored.sort(
        key=lambda item: (
            int(item.get("_score", 0)),
            str(item.get("updated_at", "")),
            str(item.get("summary", "")),
        ),
        reverse=True,
    )
    return scored[:limit]


def format_record(record: dict[str, Any]) -> str:
    lines = [f"- {record.get('summary', '')}"]
    if record.get("details"):
        lines.append(f"  details: {record['details']}")
    if record.get("goal") and record.get("goal") != record.get("summary"):
        lines.append(f"  goal: {record['goal']}")
    if record.get("choices"):
        lines.append(f"  choices: {', '.join(flatten_list(record['choices']))}")
    if record.get("constraints"):
        lines.append(f"  constraints: {', '.join(flatten_list(record['constraints']))}")
    if record.get("open_questions"):
        lines.append(f"  open questions: {', '.join(flatten_list(record['open_questions']))}")
    if record.get("files"):
        lines.append(f"  files: {', '.join(flatten_list(record['files']))}")
    if record.get("tags"):
        lines.append(f"  tags: {', '.join(flatten_list(record['tags']))}")
    return "\n".join(lines)


def render_recall(records: list[dict[str, Any]]) -> str:
    if not records:
        return "# Relevant Memory\n\nNo matching memory found."

    grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in SECTION_ORDER}
    for record in records:
        kind = str(record.get("kind"))
        grouped.setdefault(kind, []).append(record)

    sections = ["# Relevant Memory"]
    for kind in SECTION_ORDER:
        items = grouped.get(kind, [])
        if not items:
            continue
        sections.append(f"\n## {SECTION_TITLES.get(kind, kind.title())}")
        for item in items:
            sections.append(format_record(item))
    return "\n".join(sections)


def run_git(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(since: str | None) -> list[str]:
    if since:
        files = run_git(["diff", "--name-only", "--relative", f"{since}...HEAD"])
        return sorted(dict.fromkeys(files))

    files: list[str] = []
    files.extend(run_git(["diff", "--name-only", "--relative"]))
    files.extend(run_git(["diff", "--name-only", "--relative", "--cached"]))
    files.extend(run_git(["ls-files", "--others", "--exclude-standard"]))
    return sorted(dict.fromkeys(files))


def render_closeout(files: list[str], recalled: list[dict[str, Any]]) -> str:
    sections = ["# Closeout Check"]

    if files:
        sections.append("\n## Changed Files")
        for file_path in files:
            sections.append(f"- {file_path}")
    else:
        sections.append("\n## Changed Files")
        sections.append("No changed files detected.")

    if recalled:
        sections.append("\n## Memory Touching Those Files")
        grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in SECTION_ORDER}
        for record in recalled:
            grouped.setdefault(str(record.get("kind")), []).append(record)

        for kind in SECTION_ORDER:
            items = grouped.get(kind, [])
            if not items:
                continue
            sections.append(f"\n### {SECTION_TITLES.get(kind, kind.title())}")
            for item in items:
                sections.append(format_record(item))
    else:
        sections.append("\n## Memory Touching Those Files")
        sections.append("No existing memory matched the changed files.")

    sections.append("\n## Capture Checklist")
    sections.append("- Save explicit repo-wide technical choices as `decision`.")
    sections.append("- Save stable implementation rules as `convention`.")
    sections.append("- Save recurring gotchas as `pitfall`.")
    sections.append("- Save user-specific style or workflow preferences as `preference`.")
    sections.append("- Update the active task packet if the goal or constraints changed.")
    return "\n".join(sections)


def print_json(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=True))
    sys.stdout.write("\n")


def handle_capture(args: argparse.Namespace) -> None:
    payload = read_stdin_if_available()
    if payload:
        raw_records = parse_json_payload(payload)
    else:
        raw_records = [build_capture_record(args)]

    normalized = [normalize_record(record) for record in raw_records]
    created, updated = upsert_records(normalized)

    if args.format == "json":
        print_json({"created": created, "updated": updated, "records": normalized})
        return

    sys.stdout.write(f"Captured {len(normalized)} record(s): {created} created, {updated} updated.\n")


def handle_intake(args: argparse.Namespace) -> None:
    payload = read_stdin_if_available()
    if payload:
        raw_records = parse_json_payload(payload)
    else:
        raw_records = [build_session_record(args)]

    normalized = [normalize_record(record) for record in raw_records]
    created, updated = upsert_records(normalized)

    if args.format == "json":
        print_json({"created": created, "updated": updated, "records": normalized})
        return

    sys.stdout.write(f"Stored {len(normalized)} task packet(s): {created} created, {updated} updated.\n")


def handle_recall(args: argparse.Namespace) -> None:
    records = recall_records(args.files or [], args.tags or [], args.query, args.limit)
    if args.format == "json":
        print_json({"records": records})
        return
    sys.stdout.write(f"{render_recall(records)}\n")


def handle_closeout(args: argparse.Namespace) -> None:
    files = changed_files(args.since)
    recalled = recall_records(files, [], None, args.limit) if files else []

    if args.format == "json":
        print_json({"changed_files": files, "records": recalled})
        return

    sys.stdout.write(f"{render_closeout(files, recalled)}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cursor starter pack memory helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="write shared or local memory")
    capture.add_argument("--kind", choices=sorted(KIND_TO_FILE))
    capture.add_argument("--summary")
    capture.add_argument("--details")
    capture.add_argument("--files", nargs="*")
    capture.add_argument("--tags", nargs="*")
    capture.add_argument("--status")
    capture.add_argument("--expires-at")
    capture.add_argument("--source")
    capture.add_argument("--format", choices=["text", "json"], default="text")
    capture.set_defaults(func=handle_capture)

    intake = subparsers.add_parser("intake", help="store a task packet in local session memory")
    intake.add_argument("--summary")
    intake.add_argument("--goal")
    intake.add_argument("--details")
    intake.add_argument("--files", nargs="*")
    intake.add_argument("--constraints", nargs="*")
    intake.add_argument("--choices", nargs="*")
    intake.add_argument("--acceptance", nargs="*")
    intake.add_argument("--open-questions", nargs="*")
    intake.add_argument("--tags", nargs="*")
    intake.add_argument("--status", default="active")
    intake.add_argument("--format", choices=["text", "json"], default="text")
    intake.set_defaults(func=handle_intake)

    recall = subparsers.add_parser("recall", help="read the most relevant memory")
    recall.add_argument("--query")
    recall.add_argument("--files", nargs="*")
    recall.add_argument("--tags", nargs="*")
    recall.add_argument("--limit", type=int, default=12)
    recall.add_argument("--format", choices=["markdown", "json"], default="markdown")
    recall.set_defaults(func=handle_recall)

    closeout = subparsers.add_parser("closeout", help="inspect changed files and related memory")
    closeout.add_argument("--since")
    closeout.add_argument("--limit", type=int, default=8)
    closeout.add_argument("--format", choices=["markdown", "json"], default="markdown")
    closeout.set_defaults(func=handle_closeout)

    return parser


def main() -> int:
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
