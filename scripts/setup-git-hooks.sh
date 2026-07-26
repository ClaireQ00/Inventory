#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$ROOT_DIR/.git/hooks"

if [[ ! -d "$ROOT_DIR/.git" ]]; then
  echo "Not a git repository: $ROOT_DIR"
  exit 1
fi

if [[ ! -d "$HOOKS_DIR" ]]; then
  echo "Creating Git hooks directory: $HOOKS_DIR"
  mkdir -p "$HOOKS_DIR"
fi

install_hook() {
  local name="$1"
  local source="$ROOT_DIR/scripts/hooks/${name}.sample"
  local dest="$HOOKS_DIR/$name"
  if [[ ! -f "$source" ]]; then
    echo "Skipping $name: $source not found"
    return
  fi
  cp "$source" "$dest"
  chmod +x "$dest"
  echo "Installed $name"
}

install_hook pre-commit
install_hook pre-push
install_hook commit-msg

echo "Git hooks installation complete."
