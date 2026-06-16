#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to package skill-manage." >&2
  exit 1
fi

case "${1:-}" in
  --dry-run)
    npm pack --dry-run
    ;;
  "")
    npm pack --dry-run
    npm pack
    ;;
  -h | --help)
    cat <<'EOF'
Usage:
  scripts/package.sh           Run npm pack dry-run, then create the tarball
  scripts/package.sh --dry-run Check package contents without creating a tarball
EOF
    ;;
  *)
    echo "Unknown option: $1" >&2
    echo "Run scripts/package.sh --help for usage." >&2
    exit 1
    ;;
esac
