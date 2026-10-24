# Release Process

This page documents how `sonar-tools` releases are published. It is intended for maintainers.

## PyPI release (automated)

PyPI publishing is handled by the `release` GitHub Actions workflow (`.github/workflows/release.yml`), triggered when a **GitHub Release is published**.

The workflow:
1. Checks out the code and builds the package with Poetry.
2. Verifies that the release tag (e.g. `v3.22`) matches the version declared in `pyproject.toml`. The job fails if they differ.
3. Publishes the built distribution to PyPI using [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC via `pypa/gh-action-pypi-publish`). No PyPI API token is stored as a GitHub secret.

To cut a PyPI release:
1. Bump the `version` field in `pyproject.toml` (and `sonar/version.py` if applicable) and merge to `master`.
2. Create a GitHub Release with a tag `v<version>` (e.g. `v3.22`) pointing at that commit.
3. Publishing the release triggers the workflow automatically; progress and result are visible under the repo's **Actions** tab.

### One-time setup (already done by the maintainer, documented for reference)

- A `pypi` GitHub Environment must exist on the repository (used by the `publish-pypi` job for protection rules, e.g. required reviewers).
- The PyPI project (`sonar-tools`) must register this repository/workflow/environment as a trusted publisher: **pypi.org → sonar-tools project → Publishing → Add a new publisher**, with owner `okorach`, repository `sonar-tools`, workflow `release.yml`, environment `pypi`.

## Docker Hub release (manual, unchanged)

Docker Hub publishing and the final `twine`-based upload are still performed locally via `conf/release.sh`, which also pushes the `olivierkorach/sonar-tools` image to Docker Hub. This script is unaffected by the GitHub Actions PyPI pipeline above.
