#!/bin/bash

# Release script for pyepwmorph
# Usage: ./release.sh [patch|minor|major]
#
# Prerequisites: uv, git, a clean working tree on main
# The GitHub Actions workflow (publish.yml) handles PyPI publishing
# when a GitHub Release is created from the pushed tag.

set -euo pipefail

BUMP_TYPE=${1:-patch}

case "$BUMP_TYPE" in
    patch|minor|major) ;;
    *)
        echo "ERROR: Invalid bump type '$BUMP_TYPE'. Use patch, minor, or major."
        exit 1
        ;;
esac

echo "Checking git status..."
if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: The working tree has uncommitted changes."
    echo "Commit or stash them before releasing so the tag matches what you reviewed."
    git status --short
    exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo "ERROR: Releases are cut from main, but you are on '$BRANCH'."
    exit 1
fi

echo "Pulling latest changes..."
git pull --ff-only origin main

echo "Running lint..."
uv run --extra dev ruff check pyepwmorph tests gui

echo "Running tests..."
uv run --extra dev pytest

# Get current version from pyproject.toml
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo "Current version: $CURRENT_VERSION"

MAJOR=$(echo "$CURRENT_VERSION" | cut -d. -f1)
MINOR=$(echo "$CURRENT_VERSION" | cut -d. -f2)
PATCH=$(echo "$CURRENT_VERSION" | cut -d. -f3)

if [ "$BUMP_TYPE" = "major" ]; then
    NEW_VERSION="$((MAJOR + 1)).0.0"
elif [ "$BUMP_TYPE" = "minor" ]; then
    NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
else
    NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
fi

echo "New version: $NEW_VERSION"

if ! grep -q "^## $NEW_VERSION" CHANGELOG.md; then
    echo "ERROR: CHANGELOG.md has no '## $NEW_VERSION' section."
    echo "Write the release notes before tagging."
    exit 1
fi

# Update version in pyproject.toml (single source of truth)
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
else
    sed -i "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
fi

# Regenerate lock file with new version
uv lock

echo "Building package..."
rm -rf dist/
uv build

# Commit, tag, and push
git add pyproject.toml uv.lock
git commit -m "Bump version: $CURRENT_VERSION -> $NEW_VERSION"
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"

echo "Pushing changes and tags..."
git push origin main --follow-tags

echo "Released version $NEW_VERSION"
echo "Create a GitHub release at:"
echo "  https://github.com/justinfmccarty/pyepwmorph/releases/new?tag=v$NEW_VERSION"
echo ""
echo "PyPI publish will trigger automatically when the GitHub Release is created."
