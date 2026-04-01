# Cursor Memory Engine

A plug-and-play starter pack for Cursor that adds durable repo memory, private local memory, and a compact delegation workflow without requiring Mulch at runtime.

## What It Gives You

- always-on Cursor rules for concise, direct collaboration
- shared git-backed repo memory in `.cursor-memory/shared/`
- local private memory in `.cursor-memory/local/`
- repo-local helper scripts for intake, recall, capture, and closeout
- a lightweight subagent handoff pattern based on compact task packets

## One-Line Install

Run this from the root of the repo you want Cursor to work in:

```sh
curl -fsSL https://raw.githubusercontent.com/N3ur0sis/cursor-memory-engine/main/install.sh | sh
```

That installs:

- `.cursor/rules/*.mdc`
- `.cursor-memory/`
- `tools/agent/`
- the shared-memory merge rule in `.gitattributes`

The installer is safe by default:

- it does not overwrite different managed files unless you pass `--force`
- it seeds empty memory files but preserves existing memory content
- it does not require Bun, Node, or Mulch in the target repo

## Local Install

If you cloned this repo, you can install the pack into another repo with:

```sh
./install.sh --dir /path/to/target/repo
```

Or install into the current repo root:

```sh
./install.sh
```

## Updating An Existing Install

Re-run the installer from the target repo root:

```sh
curl -fsSL https://raw.githubusercontent.com/N3ur0sis/cursor-memory-engine/main/install.sh | sh -s -- --force
```

Use `--force` only when you want the latest managed rule and script files to replace local edits.

## Publishing This As Its Own Repo

This directory is designed to become the root of a standalone repository.

To publish it separately:

1. Copy the contents of this directory to the root of a new repo.
2. Push that repo to GitHub.
3. The one-line installer will work from the published `install.sh`.

The default installer target is:

- [`N3ur0sis/cursor-memory-engine`](https://github.com/N3ur0sis/cursor-memory-engine)

If you publish from a different repo or branch, set `CURSOR_MEMORY_REPO` or `CURSOR_MEMORY_REF` when running the installer.

## Memory Model

### Shared Memory

Use shared memory for durable repo truth:

- decisions the team wants preserved
- implementation conventions
- repeatable workflows
- important references
- recurring pitfalls

### Local Memory

Use local memory for developer-specific or short-lived context:

- active task packets
- private workflow preferences
- temporary carry-over that should not become team policy

## How It Feels In Cursor

After install, people keep using Cursor normally.

The installed rules make the workflow more consistent by nudging the agent to:

- normalize bigger requests into task packets
- recall relevant shared and local memory before acting
- delegate with compact packets instead of raw prompts
- capture durable repo decisions and conventions before finishing

## Recommended Workflow

1. For non-trivial tasks, normalize the request into a task packet.
2. Recall relevant memory before planning or editing.
3. Delegate with the compact packet instead of only forwarding the raw user prompt.
4. Capture durable choices as you go.
5. Run closeout before wrapping up.

## Helper Scripts

### Recall

```sh
tools/agent/recall.sh --files src/app.ts src/db.ts --query "error handling"
```

### Intake

```sh
tools/agent/intake.sh \
  --goal "Add retry handling to the sync job" \
  --files src/sync.ts src/jobs/retry.ts \
  --constraints "Keep existing API" "Do not add new dependencies"
```

### Capture

```sh
cat <<'EOF' | tools/agent/capture.sh
{
  "kind": "decision",
  "summary": "Use retries with bounded exponential backoff",
  "details": "The sync job talks to flaky external APIs, so retries should be capped and jittered.",
  "files": ["src/sync.ts", "src/jobs/retry.ts"],
  "tags": ["sync", "reliability"]
}
EOF
```

### Closeout

```sh
tools/agent/closeout.sh
```

## What Gets Installed

### Managed Files

These are installed and updated by the starter pack:

- `.cursor/rules/00-core-behavior.mdc`
- `.cursor/rules/10-intake-and-planning.mdc`
- `.cursor/rules/20-memory-recall.mdc`
- `.cursor/rules/30-delegation.mdc`
- `.cursor-memory/config.yaml`
- `.cursor-memory/README.md`
- `.cursor-memory/shared/README.md`
- `.cursor-memory/local/README.md`
- `.cursor-memory/local/.gitignore`
- `tools/agent/memory_tool.py`
- `tools/agent/intake.sh`
- `tools/agent/recall.sh`
- `tools/agent/capture.sh`
- `tools/agent/closeout.sh`

### Seeded Memory Files

These are created only when missing or empty:

- `.cursor-memory/shared/decisions.jsonl`
- `.cursor-memory/shared/conventions.jsonl`
- `.cursor-memory/shared/workflows.jsonl`
- `.cursor-memory/shared/references.jsonl`
- `.cursor-memory/shared/pitfalls.jsonl`
- `.cursor-memory/local/session.jsonl`
- `.cursor-memory/local/user-preferences.jsonl`

## Record Shape

The helper scripts accept JSON objects or arrays. The core shape is:

```json
{
  "kind": "decision|convention|workflow|reference|pitfall|session|preference",
  "summary": "short durable statement",
  "details": "optional explanation",
  "files": ["optional/file/path.ts"],
  "tags": ["optional-tag"],
  "status": "active"
}
```

Useful optional fields:

- `expires_at`
- `source`
- `constraints`
- `choices`
- `acceptance`
- `open_questions`

## Notes

- The Python helper uses simple JSONL files and file locks for safe writes.
- `.gitattributes` sets `merge=union` for shared memory files to keep branch merges simple.
- `config.yaml` documents the intended scoring and retention defaults for humans and future tooling.
- The default online installer target is [`N3ur0sis/cursor-memory-engine`](https://github.com/N3ur0sis/cursor-memory-engine).
