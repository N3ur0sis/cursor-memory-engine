# Cursor Memory

This directory stores durable memory for the Cursor starter pack.

## Shared Memory

Files in `.cursor-memory/shared/` are meant to be committed to git and shared with the team.

- `decisions.jsonl`: repo-wide technical choices and their rationale
- `conventions.jsonl`: stable implementation rules the agent should follow
- `workflows.jsonl`: repeatable procedures worth reusing across tasks
- `references.jsonl`: important files, modules, endpoints, or docs
- `pitfalls.jsonl`: recurring mistakes, gotchas, and how to avoid them

## Local Memory

Files in `.cursor-memory/local/` are private to each developer and should stay uncommitted.

- `session.jsonl`: active task packets, short-term carry-over, and current constraints
- `user-preferences.jsonl`: developer-specific preferences that should not become repo policy

## Record Shape

Each line is a JSON object. The smallest useful record looks like this:

```json
{
  "kind": "decision",
  "summary": "Use Bun for local CLI execution",
  "details": "The repo already executes TypeScript directly with Bun.",
  "files": ["src/cli.ts"],
  "tags": ["runtime", "cli"]
}
```

Useful optional fields:

- `status`: `active`, `archived`, or `superseded`
- `expires_at`: ISO timestamp for temporary memory
- `source`: why the record was created
- `constraints`, `choices`, `acceptance`, `open_questions`: especially useful for `session` records

The helper scripts in `tools/agent/` read and write these files for recall, capture, intake, and closeout.
