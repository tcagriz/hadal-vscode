# Releasing Hadal for VS Code

This package is synchronized from `vscode/` in
[tcagriz/hadal-theme](https://github.com/tcagriz/hadal-theme). Publish only from
the protected mirror's `main` branch after the source and mirror pull requests
have merged.

## Prepare

1. In `hadal-theme`, update `vscode/package.json`,
   `vscode/CHANGELOG.md` and every user-visible package change together.
2. Complete the package checks and mirror synchronization. Do not release
   directly from the monorepo or an unmerged feature branch.
3. In this mirror, confirm that `main` is clean and current:

   ```sh
   git switch main
   git pull --ff-only
   test -z "$(git status --porcelain)"
   ```

4. Validate the intended version without creating a tag:

   ```sh
   version="$(node -p "require('./package.json').version")"
   python3 scripts/release.py metadata --kind vscode --tag "v$version"
   python3 tests/publish_workflow_test.py
   npx --yes @vscode/vsce@4.1.1 package --out "/tmp/hadal-theme-$version.vsix"
   ```

## Publish

Create and push one annotated release tag:

```sh
version="$(node -p "require('./package.json').version")"
git tag -a "v$version" -m "Hadal for VS Code $version"
git push origin "v$version"
```

The tag triggers `.github/workflows/publish.yml`. The workflow:

1. Requires the tag to contain only `vX.Y.Z`, match `package.json`, match a
   `CHANGELOG.md` heading and be reachable from `main`.
2. Builds and fingerprints the VSIX once.
3. Creates or verifies the immutable GitHub release asset without overwriting an
   existing asset.
4. Requests the protected `production` approval.
5. Downloads and verifies that release asset. If the version is already present,
   it compares Marketplace's VSIX SHA-256 with the release asset and succeeds
   only when they match. Otherwise it publishes with VS Code trusted publishing.

Watch the run and approve the `production` deployment:

```sh
gh run list --repo tcagriz/hadal-vscode --workflow publish.yml --event push
```

## Rerun and recovery

Use **Re-run jobs** on the workflow for the existing tag. Do not delete, recreate
or move a release tag. The workflow compares a pre-existing release asset
byte-for-byte and verifies a published Marketplace version by SHA-256;
`--skip-duplicate` is retained only to close a concurrent publish race without
overwriting a version.

If the tag or version is wrong, do not mutate the existing tag. Fix the source
change through a pull request, increment the package version and create a new
tag. No package publication occurs from `workflow_dispatch`.
