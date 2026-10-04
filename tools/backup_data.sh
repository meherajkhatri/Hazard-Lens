#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:-$root/backups/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$destination"
sources=0

if [[ -f "$root/backend/data/call_help.sqlite3" ]]; then
  sqlite3 "$root/backend/data/call_help.sqlite3" ".backup '$destination/call_help.sqlite3'"
  sources=$((sources + 1))
fi

if [[ -d "$root/backend/data/snapshots" ]]; then
  cp -R "$root/backend/data/snapshots" "$destination/"
  sources=$((sources + 1))
fi

if [[ "$sources" -eq 0 ]]; then
  rmdir "$destination" 2>/dev/null || true
  printf 'No local SQLite database or snapshots found; backup not created.\n' >&2
  exit 1
fi

(
  cd "$destination"
  find . -type f -print | sort | while IFS= read -r file; do
    shasum -a 256 "$file"
  done > MANIFEST.sha256
)
printf 'Backup written to %s\n' "$destination"
