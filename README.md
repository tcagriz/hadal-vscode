# Hadal for VS Code

Deep blue dark theme, based on the VS Code Abyss color theme (MIT, Microsoft).
It covers the workbench, editor, terminal and TextMate token colors.

## Install

From a `.vsix` file:

```sh
code --install-extension hadal-theme-0.1.0.vsix
```

Then run **Preferences: Color Theme** and select **Hadal**.

## Development

This extension is developed inside the
[Hadal Theme Suite](https://github.com/tcagriz/hadal-theme) monorepo and mirrored here with
`git subtree split`. `themes/hadal-color-theme.json` is generated from the suite's
`palette/palette.json`; do not edit it by hand. Send changes to the monorepo.

Try it without installing: open this folder in VS Code and press `F5` to start an
Extension Development Host. Build a package with `npx @vscode/vsce package`.

## License

MIT. The base colors come from the Abyss theme in
[microsoft/vscode](https://github.com/microsoft/vscode), see the LICENSE file.
