#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -d .git ]]; then
  echo "Git repository already initialized."
  git status --short
  exit 0
fi

echo "Initializing git repository..."
git init

echo "Adding files..."
git add .

echo "Committing initial version..."
git commit -m "chore: initialize inventory project with docs, scripts, SQL schema, and CI setup"

echo "Git repository initialized."

echo "To publish to a private GitHub repo, create the repo first and then run:"
echo "  git remote add origin <your-private-repo-url>"
echo "  git branch -M main"
echo "  git push -u origin main"
