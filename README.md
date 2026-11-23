# Hadal for VS Code

Deep blue dark theme based on the VS Code Abyss theme. Hadal covers the
workbench, editor, terminal and TextMate token colors.

## Install

Install from the
[Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=tcagriz.hadal-theme)
or search for **Hadal** in the VS Code Extensions view.

Command line:

```sh
code --install-extension tcagriz.hadal-theme
```

Then open the Command Palette, run **Preferences: Color Theme** and select
**Hadal**.

## Install from a VSIX file

Download the latest `.vsix` from
[GitHub Releases](https://github.com/tcagriz/hadal-vscode/releases/latest) and run:

```sh
code --install-extension hadal-theme-<version>.vsix
```

## Requirements

- VS Code 1.80 or newer
- A terminal with true-color support is recommended for the closest terminal
  appearance

## Included

- Editor, workbench and UI colors
- Syntax highlighting
- Integrated terminal ANSI colors
- Semantic highlighting

## Update and uninstall

Use the VS Code Extensions view to update or uninstall Hadal. Command-line
uninstall:

```sh
code --uninstall-extension tcagriz.hadal-theme
```

## Support and source

Ask installation and usage questions in
[Hadal Discussions](https://github.com/tcagriz/hadal-theme/discussions). Report
reproducible VS Code-specific bugs through the
[Hadal issue chooser](https://github.com/tcagriz/hadal-theme/issues/new/choose).
Source changes are made in the
[Hadal Theme Suite](https://github.com/tcagriz/hadal-theme) monorepo and mirrored
here. Suspected vulnerabilities must use the monorepo's
[private security report form](https://github.com/tcagriz/hadal-theme/security/advisories/new).

## License

MIT. The base colors come from the Abyss theme in
[microsoft/vscode](https://github.com/microsoft/vscode); see the
[license notice](LICENSE).
