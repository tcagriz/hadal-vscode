# Hadal for VS Code instructions

## Mirror policy

- This repository is a synchronized mirror of the `vscode/` directory in
  [tcagriz/hadal-theme](https://github.com/tcagriz/hadal-theme).
- Make primary source changes in `hadal-theme/vscode/`, sync them with
  `scripts/sync.sh vscode`, and submit mirror changes through a pull request.
- Never push directly to `main` or publish from an ad-hoc commit.
- Bug reports and feature requests belong in the `hadal-theme` monorepo.
  Suspected vulnerabilities must use its private vulnerability report.
- `themes/hadal-color-theme.json` is generated from
  `palette/palette.json` by the monorepo generator. Do not hand-edit it.
- Keep theme mappings in the package manifest and documentation consistent
  with the generated theme.

## Development rules

- Preserve VS Code 1.80+ compatibility declared in `package.json` unless an
  issue explicitly changes the supported version.
- Keep the extension ID, publisher, version, changelog, README and release
  workflow consistent.
- Follow `RELEASING.md` for tag-driven package releases. Never add a manual
  publication path or republish by moving/deleting an immutable release tag.
- Preserve workbench, editor, syntax, semantic-token and terminal coverage.
- Do not introduce one-off colors that bypass the shared Hadal palette.
- Never commit Marketplace credentials, tokens or OIDC configuration values.

## Validation

Run from the extension root:

```sh
python3 -m json.tool package.json > /dev/null
python3 -m json.tool themes/hadal-color-theme.json > /dev/null
python3 tests/publish_workflow_test.py
npx --yes @vscode/vsce@4.1.1 package --out /tmp/hadal-theme.vsix
```

Before publishing, verify that the manifest version, changelog entry and
release tag agree. Publishing must continue to require approval through the
protected `production` environment.
