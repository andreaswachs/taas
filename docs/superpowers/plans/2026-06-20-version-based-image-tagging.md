# Version-Based Image Tagging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SHA/latest image tagging with semantic versioning from `pyproject.toml`, and add a PR check to enforce version bumps.

**Architecture:** Extract version from `pyproject.toml` during CI and use it as the primary image tag. A separate workflow validates that the version was bumped on every PR to `main`.

**Tech Stack:** GitHub Actions, Docker Buildx, `yq` for YAML parsing

---

## File Structure

- Modify: `.github/workflows/release.yml` — extract version, use as image tag
- Create: `.github/workflows/version-bump.yml` — PR check for version bump

---

### Task 1: Update release workflow to use version from pyproject.toml

**Files:**
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Add version extraction step after checkout**

Insert a new step after "Checkout repository" (line 19) and before "Set up QEMU" (line 21):

```yaml
    - name: Extract version from pyproject.toml
      run: |
        VERSION=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
        echo "VERSION=$VERSION" >> $GITHUB_ENV
```

- [ ] **Step 2: Update image tags to include version**

Replace the `tags:` block (lines 45-47) with:

```yaml
        tags: |
          ghcr.io/${{ github.repository_owner }}/${{ env.REPOSITORY_NAME }}:${{ env.VERSION }}
          ghcr.io/${{ github.repository_owner }}/${{ env.REPOSITORY_NAME }}:${{ github.sha }}
          ghcr.io/${{ github.repository_owner }}/${{ env.REPOSITORY_NAME }}:latest
```

- [ ] **Step 3: Update Trivy scan to use version tag**

Replace the `image-ref` value (line 55) with:

```yaml
        image-ref: 'ghcr.io/${{ github.repository_owner }}/${{ env.REPOSITORY_NAME }}:${{ env.VERSION }}'
```

- [ ] **Step 4: Update GitHub Release to use version tag**

Replace the `create-release` job steps (lines 82-89) with:

```yaml
    - name: Extract version from pyproject.toml
      run: |
        VERSION=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
        echo "VERSION=$VERSION" >> $GITHUB_ENV

    - name: Generate GitHub Release
      uses: softprops/action-gh-release@v1
      with:
        name: Release ${{ env.VERSION }}
        tag_name: ${{ env.VERSION }}
        draft: false
        prerelease: false
        generate_release_notes: true
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: use pyproject.toml version for image tags"
```

---

### Task 2: Create version bump check workflow

**Files:**
- Create: `.github/workflows/version-bump.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: Version Bump Check

on:
  pull_request:
    branches: [ main ]

jobs:
  check-version-bump:
    runs-on: ubuntu-latest
    steps:
    - name: Checkout PR branch
      uses: actions/checkout@v4

    - name: Extract PR version
      run: |
        PR_VERSION=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
        echo "PR_VERSION=$PR_VERSION" >> $GITHUB_ENV

    - name: Fetch main branch
      run: git fetch origin main

    - name: Extract main version
      run: |
        MAIN_VERSION=$(git show origin/main:pyproject.toml | grep -m1 '^version' | cut -d'"' -f2)
        echo "MAIN_VERSION=$MAIN_VERSION" >> $GITHUB_ENV

    - name: Check version was bumped
      run: |
        if [ "$PR_VERSION" = "$MAIN_VERSION" ]; then
          echo "ERROR: Version was not bumped. Current: $MAIN_VERSION"
          echo "Please bump the version in pyproject.toml before merging."
          exit 1
        fi
        echo "Version bumped: $MAIN_VERSION -> $PR_VERSION"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/version-bump.yml
git commit -m "ci: add PR check for version bump"
```
