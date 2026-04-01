#!/usr/bin/env sh
set -eu

REPO_SLUG="${CURSOR_MEMORY_REPO:-N3ur0sis/cursor-memory-engine}"
REF="${CURSOR_MEMORY_REF:-main}"
TARGET_DIR="${CURSOR_MEMORY_TARGET_DIR:-$PWD}"
SOURCE_DIR="${CURSOR_MEMORY_SOURCE_DIR:-}"
FORCE=0
QUIET=0

CREATED=0
UPDATED=0
SEEDED=0
SKIPPED=0

TMPDIR_CREATED=""

cleanup() {
  if [ -n "${TMPDIR_CREATED:-}" ] && [ -d "$TMPDIR_CREATED" ]; then
    rm -rf "$TMPDIR_CREATED"
  fi
}

trap cleanup EXIT INT TERM HUP

say() {
  if [ "$QUIET" -eq 0 ]; then
    printf '%s\n' "$1"
  fi
}

warn() {
  printf '%s\n' "warning: $1" >&2
}

die() {
  printf '%s\n' "error: $1" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: install.sh [options]

Install the Cursor Memory Starter Pack into a target repository root.

Options:
  --dir <path>     Install into this directory instead of the current directory
  --ref <ref>      Git ref to download when installing remotely (default: $REF)
  --repo <slug>    GitHub repo slug to download from (default: $REPO_SLUG)
  --force          Overwrite managed starter-pack files if they already exist
  --quiet          Reduce installer output
  --help           Show this help

Examples:
  ./install.sh
  ./install.sh --dir ../my-project
  curl -fsSL https://raw.githubusercontent.com/N3ur0sis/cursor-memory-engine/main/install.sh | sh
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir)
      [ "$#" -ge 2 ] || die "--dir requires a value"
      TARGET_DIR="$2"
      shift 2
      ;;
    --ref)
      [ "$#" -ge 2 ] || die "--ref requires a value"
      REF="$2"
      shift 2
      ;;
    --repo)
      [ "$#" -ge 2 ] || die "--repo requires a value"
      REPO_SLUG="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

resolve_script_dir() {
  case "$0" in
    /*) dirname "$0" ;;
    */*) dirname "$PWD/$0" ;;
    *) printf '%s\n' "" ;;
  esac
}

SCRIPT_DIR=$(resolve_script_dir)

download_source() {
  TMPDIR_CREATED=$(mktemp -d)
  ARCHIVE_URL="https://codeload.github.com/$REPO_SLUG/tar.gz/$REF"

  say "Downloading starter pack from $REPO_SLUG@$REF"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$TMPDIR_CREATED"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$ARCHIVE_URL" | tar -xz -C "$TMPDIR_CREATED"
  else
    die "Either curl or wget is required for remote installation."
  fi

  set -- "$TMPDIR_CREATED"/*
  [ -d "$1" ] || die "Failed to unpack remote starter pack."
  SOURCE_DIR="$1"
}

if [ -n "$SOURCE_DIR" ]; then
  :
elif [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/.cursor-memory/config.yaml" ]; then
  SOURCE_DIR="$SCRIPT_DIR"
else
  download_source
fi

[ -d "$SOURCE_DIR" ] || die "Source directory not found: $SOURCE_DIR"
mkdir -p "$TARGET_DIR"

SOURCE_DIR=$(cd "$SOURCE_DIR" && pwd)
TARGET_DIR=$(cd "$TARGET_DIR" && pwd)

if [ ! -d "$TARGET_DIR/.git" ]; then
  warn "Target directory does not look like a git repository: $TARGET_DIR"
  warn "Continuing anyway. The shared memory files and .gitattributes will still be installed."
fi

copy_managed_file() {
  rel="$1"
  src="$SOURCE_DIR/$rel"
  dest="$TARGET_DIR/$rel"
  mkdir -p "$(dirname "$dest")"

  if [ ! -e "$dest" ]; then
    cp "$src" "$dest"
    CREATED=$((CREATED + 1))
    say "created $rel"
    return
  fi

  if cmp -s "$src" "$dest"; then
    say "kept $rel"
    return
  fi

  if [ "$FORCE" -eq 1 ]; then
    cp "$src" "$dest"
    UPDATED=$((UPDATED + 1))
    say "updated $rel"
  else
    SKIPPED=$((SKIPPED + 1))
    warn "kept existing $rel (use --force to overwrite)"
  fi
}

seed_file() {
  rel="$1"
  src="$SOURCE_DIR/$rel"
  dest="$TARGET_DIR/$rel"
  mkdir -p "$(dirname "$dest")"

  if [ ! -e "$dest" ] || [ ! -s "$dest" ]; then
    if [ -f "$src" ]; then
      cp "$src" "$dest"
    else
      : > "$dest"
    fi
    SEEDED=$((SEEDED + 1))
    say "seeded $rel"
  else
    say "preserved $rel"
  fi
}

ensure_executable() {
  path="$TARGET_DIR/$1"
  if [ -e "$path" ]; then
    chmod +x "$path"
  fi
}

ensure_line() {
  file="$1"
  line="$2"
  mkdir -p "$(dirname "$file")"
  if [ ! -f "$file" ]; then
    printf '%s\n' "$line" > "$file"
    CREATED=$((CREATED + 1))
    say "created $(basename "$file")"
    return
  fi

  if grep -Fqx "$line" "$file"; then
    say "kept $(basename "$file")"
    return
  fi

  printf '\n%s\n' "$line" >> "$file"
  UPDATED=$((UPDATED + 1))
  say "updated $(basename "$file")"
}

for rel in \
  ".cursor/rules/00-core-behavior.mdc" \
  ".cursor/rules/10-intake-and-planning.mdc" \
  ".cursor/rules/20-memory-recall.mdc" \
  ".cursor/rules/30-delegation.mdc" \
  ".cursor-memory/README.md" \
  ".cursor-memory/config.yaml" \
  ".cursor-memory/shared/README.md" \
  ".cursor-memory/local/README.md" \
  ".cursor-memory/local/.gitignore" \
  "tools/agent/memory_tool.py" \
  "tools/agent/intake.sh" \
  "tools/agent/recall.sh" \
  "tools/agent/capture.sh" \
  "tools/agent/closeout.sh"
do
  copy_managed_file "$rel"
done

for rel in \
  ".cursor-memory/shared/decisions.jsonl" \
  ".cursor-memory/shared/conventions.jsonl" \
  ".cursor-memory/shared/workflows.jsonl" \
  ".cursor-memory/shared/references.jsonl" \
  ".cursor-memory/shared/pitfalls.jsonl" \
  ".cursor-memory/local/session.jsonl" \
  ".cursor-memory/local/user-preferences.jsonl"
do
  seed_file "$rel"
done

ensure_executable "tools/agent/memory_tool.py"
ensure_executable "tools/agent/intake.sh"
ensure_executable "tools/agent/recall.sh"
ensure_executable "tools/agent/capture.sh"
ensure_executable "tools/agent/closeout.sh"

ensure_line "$TARGET_DIR/.gitattributes" ".cursor-memory/shared/*.jsonl merge=union"

say ""
say "Cursor Memory Starter Pack installed into $TARGET_DIR"
say "  managed files created: $CREATED"
say "  managed files updated: $UPDATED"
say "  seeded memory files:   $SEEDED"
say "  managed files skipped: $SKIPPED"
say ""
say "Next steps:"
say "  1. Open the target repo in Cursor."
say "  2. Keep using Cursor normally; the installed rules will guide recall, delegation, and capture."
say "  3. Use tools/agent/recall.sh before non-trivial work and tools/agent/closeout.sh before wrapping up."
