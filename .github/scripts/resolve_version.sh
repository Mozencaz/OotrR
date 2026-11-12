#!/usr/bin/env bash
# Resolves the tag to create from an optional requested version.
#   resolve_version.sh [VERSION]
# Empty VERSION -> the version of pyproject.toml. Accepts "1.2.3" or "v1.2.3"
# (optionally with a suffix: v1.2.3-beta.1). Fails if the tag already exists on origin.
# Writes version=1.2.3 and tag=v1.2.3 to $GITHUB_OUTPUT.
set -euo pipefail

project=$(sed -n 's/^version *= *"\(.*\)"/\1/p' pyproject.toml | head -n1)
requested="${1:-}"
version="${requested:-$project}"
version="${version#v}"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]]; then
    echo "::error::Invalid version \"$version\" (expected: 1.2.3 or v1.2.3-beta.1)"
    exit 1
fi
tag="v$version"

if [[ "$version" != "$project" ]]; then
    echo "::warning::$tag does not match the project version ($project, pyproject.toml / oot_rando/__init__.py): the application will show $project."
fi

if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
    echo "::error::Tag $tag already exists."
    exit 1
fi

echo "Tag: $tag (commit $(git rev-parse --short HEAD))"
{
    echo "version=$version"
    echo "tag=$tag"
} >> "${GITHUB_OUTPUT:-/dev/stdout}"
