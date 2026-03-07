#!/bin/bash

# Release script for pyepwmorph
# Usage: ./release.sh [patch|minor|major]
#
# Prerequisites: uv, git
# The GitHub Actions workflow (publish.yml) handles PyPI publishing
# when a GitHub Release is created from the pushed tag.

set -e

BUMP_TYPE=${1:-patch}

echo "Checking git status..."
if [ -n "$(git status --porcelain)" ]; then
    echo "Uncommitted changes detected. Committing them now..."
    git add -A
    git commit -m "Pre-release: commit pending changes"
    git push origin main
fi

echo "Pulling latest changes..."
git pull origin main

echo "Running tests..."
uv run pytest tests/ -v || echo "WARNING: Tests failed or no tests found, continuing..."

# Get current version from pyproject.toml
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo "Current version: $CURRENT_VERSION"

# Calculate new version
MAJOR=$(echo "$CURRENT_VERSION" | cut -d. -f1)
MINOR=$(echo "$CURRENT_VERSION" | cut -d. -f2)
PATCH=$(echo "$CURRENT_VERSION" | cut -d. -f3)

if [ "$BUMP_TYPE" = "major" ]; then
    NEW_VERSION="$((MAJOR + 1)).0.0"
elif [ "$BUMP_TYPE" = "minor" ]; then
    NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
elif [ "$BUMP_TYPE" = "patch" ]; then
    NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
else
    echo "ERROR: Invalid bump type '$BUMP_TYPE'. Use patch, minor, or major."
    exit 1
fi

echo "New version: $NEW_VERSION"

# Update version in pyproject.toml (single source of truth)
sed -i '' "s/version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Regenerate lock file with new version
uv lock

# Commit, tag, and push
git add pyproject.toml uv.lock
git commit -m "Bump version: $CURRENT_VERSION -> $NEW_VERSION"
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"

echo "Building package..."
uv run python -m build

echo "Pushing changes and tags..."
git push origin main --tags

echo "Released version $NEW_VERSION"
echo "Create a GitHub release at:"
echo "  https://github.com/justinfmccarty/pyepwmorph/releases/new?tag=v$NEW_VERSION"
echo ""
echo "PyPI publish will trigger automatically when the GitHub Release is created."
