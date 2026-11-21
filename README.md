# Hadal for VS Code

Deep blue dark theme, based on the VS Code Abyss color theme (MIT, Microsoft).
It covers the workbench, editor, terminal and TextMate token colors.

## Install

Install **Hadal** from the
[Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=tcagriz.hadal-theme)
or from the VS Code Extensions view by searching for `Hadal`.

You can also install it from the command line:

```sh
code --install-extension tcagriz.hadal-theme
```

Then run **Preferences: Color Theme** and select **Hadal**.

### Install from a VSIX file

Download the latest `.vsix` from the
[GitHub Releases](https://github.com/tcagriz/hadal-vscode/releases/latest), then run:

```sh
code --install-extension hadal-theme-<version>.vsix
```

## Development

This extension is developed inside the
[Hadal Theme Suite](https://github.com/tcagriz/hadal-theme) monorepo and mirrored here with
`git subtree split`. `themes/hadal-color-theme.json` is generated from the suite's
`palette/palette.json`; do not edit it by hand. Send changes to the monorepo.

Try it without installing: open this folder in VS Code and press `F5` to start an
Extension Development Host.

Build and inspect the package locally:

```sh
npx @vscode/vsce package
```

## Publishing

The extension is published as `tcagriz.hadal-theme` in the Visual Studio Marketplace.
The `publish.yml` workflow uses OIDC Trusted Publishing; no Personal Access Token is
stored in the repository. The Marketplace policy is configured for this repository
and workflow.

To publish a new version:

1. Update the version in `vscode/package.json` and add the changes to `vscode/CHANGELOG.md`
   in the monorepo.
2. Commit and mirror the `vscode/` subtree to `hadal-vscode` with `scripts/sync.sh vscode`.
3. Run **Actions > Publish to VS Code Marketplace > Run workflow** on `main`.

The workflow is safe to rerun for an existing version because it uses
`--skip-duplicate`.

## License

MIT. The base colors come from the Abyss theme in
[microsoft/vscode](https://github.com/microsoft/vscode), see the LICENSE file.
