# PyPI Publishing

`DJ-Sync` is set up to publish to PyPI from the GitHub release workflow using PyPI Trusted Publishing.

## One-Time PyPI Setup

1. Create or claim the `ytm-dropbox-dj-sync` project on PyPI.
2. In PyPI, add a Trusted Publisher for GitHub Actions with these values:
   - Owner: `life-efficient`
   - Repository: `DJ-Sync`
   - Workflow filename: `release.yml`
   - Environment name: `pypi`
3. In GitHub, keep using tagged releases like `v0.2.0`, `v0.2.1`, and so on.

After that, pushing a new version tag will:

- build the wheel and source distribution
- attach them to the GitHub release
- publish the same version to PyPI

## Notes

- The workflow uses OIDC Trusted Publishing, so there is no long-lived PyPI API token to store in GitHub.
- If PyPI Trusted Publishing is not configured yet, the `publish-pypi` job will fail even though the GitHub release assets will still build successfully.
- The package install name is `ytm-dropbox-dj-sync`.
