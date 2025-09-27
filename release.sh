#!/bin/bash

# Simple release script for pyepwmorph
# Usage: ./release.sh [patch|minor|major]

set -e

BUMP_TYPE=${1:-patch}

echo "🔍 Checking git status..."
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Working directory is not clean. Please commit or stash your changes."
    exit 1
fi

echo "🔄 Pulling latest changes..."
git pull origin main

echo "🧪 Running tests..."
python -m pytest tests/ -v || echo "⚠️  Tests failed or no tests found, continuing..."

echo "📦 Installing/upgrading build tools..."
pip install --upgrade bump2version build twine

echo "⬆️  Bumping version ($BUMP_TYPE)..."
# Get current version
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo "Current version: $CURRENT_VERSION"

# Calculate new version
if [ "$BUMP_TYPE" = "major" ]; then
    MAJOR=$(echo $CURRENT_VERSION | cut -d. -f1)
    NEW_VERSION="$((MAJOR + 1)).0.0"
elif [ "$BUMP_TYPE" = "minor" ]; then
    MAJOR=$(echo $CURRENT_VERSION | cut -d. -f1)
    MINOR=$(echo $CURRENT_VERSION | cut -d. -f2)
    NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
elif [ "$BUMP_TYPE" = "patch" ]; then
    MAJOR=$(echo $CURRENT_VERSION | cut -d. -f1)
    MINOR=$(echo $CURRENT_VERSION | cut -d. -f2)
    PATCH=$(echo $CURRENT_VERSION | cut -d. -f3)
    NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
fi

echo "New version: $NEW_VERSION"

# Update version in pyproject.toml
sed -i '' "s/version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Update version in .bumpversion.cfg
sed -i '' "s/current_version = $CURRENT_VERSION/current_version = $NEW_VERSION/" .bumpversion.cfg

# Commit and tag
git add pyproject.toml .bumpversion.cfg
git commit -m "Bump version: $CURRENT_VERSION → $NEW_VERSION"
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"

echo "🏗️  Building package..."
python -m build

echo "🚀 Pushing changes and tags..."
git push origin main --tags

echo "✅ Released version $NEW_VERSION"
echo "   Create a GitHub release at: https://github.com/justinfmccarty/pyepwmorph/releases/new?tag=v$NEW_VERSION"