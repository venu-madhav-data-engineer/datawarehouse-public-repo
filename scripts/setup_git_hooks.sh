#!/usr/bin/env bash
# ==============================================================================
# Setup Git Hooks Script
# ==============================================================================
# Configures local repository git hooks to ensure strict commit and push
# access controls.
# ==============================================================================

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "Setting up repository Git hooks..."

# Configure allowed repository user identity
git config user.name "venu-madhav-data-engineer"
git config user.email "with.u.venu@gmail.com"

# Ensure hooks in .githooks are executable
chmod +x .githooks/pre-commit
chmod +x .githooks/pre-push

# Set core.hooksPath to .githooks so Git automatically executes them
git config core.hooksPath .githooks

# Also copy to .git/hooks for redundancy
mkdir -p .git/hooks
cp .githooks/pre-commit .git/hooks/pre-commit
cp .githooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-commit .git/hooks/pre-push

echo "✓ Local Git hooks installed successfully in .githooks/ and .git/hooks/"
echo "✓ Git core.hooksPath configured to '.githooks'"
echo "Current committer identity:"
echo "  user.name  = $(git config user.name)"
echo "  user.email = $(git config user.email)"
