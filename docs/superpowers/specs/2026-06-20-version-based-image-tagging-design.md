# Version-Based Image Tagging Design

## Problem

The release workflow currently tags images with the commit SHA and `latest`. This makes it hard to know which version of the application a running container is, and there's no enforcement that the version is bumped with each PR.

## Solution

Use `pyproject.toml`'s `version` field as the single source of truth for image tags. Add a PR check to enforce version bumps.

## Changes

### 1. Release workflow (`.github/workflows/release.yml`)

- Extract `version` from `pyproject.toml` using a shell step
- Tag images with three tags:
  - `ghcr.io/owner/repo:0.1.0` — semantic version (immutable, used for pinning)
  - `ghcr.io/owner/repo:latest` — most recent main build (only on push to main)
  - `ghcr.io/owner/repo:<sha>` — commit traceability
- Trivy scan uses the version tag instead of `latest`

### 2. PR check workflow (`.github/workflows/version-bump.yml`)

New workflow triggered on PRs to `main`:
- Fetch `main` branch version from `pyproject.toml`
- Extract PR branch version from `pyproject.toml`
- Compare — fail with a clear error if they match
- Pass if versions differ (regardless of whether the bump is "correct" semver)

## Out of Scope

- No validation that the bump follows semver rules (e.g. patch vs minor vs major)
- No `image.yaml` file — `pyproject.toml` is the sole source of truth
- No automatic version bumping
