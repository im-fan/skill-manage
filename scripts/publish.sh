#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

usage() {
  cat <<'EOF'
Usage:
  scripts/publish.sh           Publish the current package and verify global install
  scripts/publish.sh --dry-run Run publish checks without publishing or installing
  scripts/publish.sh -h|--help Show this help

Before publishing, run:
  scripts/package.sh
EOF
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required to publish skill-manage." >&2
    exit 1
  fi
}

package_field() {
  local field="$1"
  node -e "const pkg = require('./package.json'); const value = pkg['$field']; if (!value) process.exit(1); process.stdout.write(String(value));"
}

tarball_name_for() {
  local package_name="$1"
  local package_version="$2"
  local base_name="${package_name#@}"
  base_name="${base_name//\//-}"
  printf '%s-%s.tgz' "$base_name" "$package_version"
}

ensure_current_tarball_exists() {
  local expected_tarball="$1"

  if [[ -f "$expected_tarball" ]]; then
    return
  fi

  echo "Package tarball not found: $expected_tarball" >&2
  echo "Run scripts/package.sh first, then rerun scripts/publish.sh." >&2
  exit 1
}

ensure_npm_login() {
  if npm whoami >/dev/null 2>&1; then
    local npm_user
    npm_user="$(npm whoami)"
    echo "npm logged in as: $npm_user"
    return
  fi

  echo "npm is not logged in. Starting npm login..."
  npm login
  npm whoami >/dev/null
}

case "${1:-}" in
  "")
    DRY_RUN=0
    ;;
  --dry-run)
    DRY_RUN=1
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    echo "Unknown option: $1" >&2
    echo "Run scripts/publish.sh --help for usage." >&2
    exit 1
    ;;
esac

require_command npm
require_command node

PACKAGE_NAME="$(package_field name)"
PACKAGE_VERSION="$(package_field version)"
EXPECTED_TARBALL="$(tarball_name_for "$PACKAGE_NAME" "$PACKAGE_VERSION")"

ensure_current_tarball_exists "$EXPECTED_TARBALL"

echo "Package metadata:"
npm pkg get name version files bin

echo
echo "Package contents dry run:"
npm pack --dry-run

echo
ensure_npm_login

echo
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Publish dry run:"
  npm publish --dry-run --access public
  echo "Dry run complete. No package was published or installed."
  exit 0
fi

echo "Publishing $PACKAGE_NAME@$PACKAGE_VERSION..."
npm publish --access public

echo
echo "Verifying published package:"
npm install -g "$PACKAGE_NAME"
skill-manager version
skill-manager h
