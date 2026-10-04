#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:-$root/backups/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$destination"

if [[ -f "$root/backend/data/call_help.sqlite3" ]]; then
  sqlite3 "$root/backend/data/call_help.sqlite3" ".backup '$destination/call_help.sqlite3'"
fi

if [[ -d "$root/backend/data/snapshots" ]]; then
  cp -R "$root/backend/data/snapshots" "$destination/"
fi

printf 'Backup written to %s\n' "$destination"
