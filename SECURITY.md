# Security policy

## What Wirehouse touches

- It **reads** source files in the folder you point it at. It never opens real `.env` files, only
  templates such as `.env.example`.
- It **writes** only to `wirehouse-out/` (or the folder you pass with `-o`), and `wirehouse install`
  writes `wirehouse/SKILL.md` into your agents' skills folders (`~/.agents/skills` plus each agent it
  finds, or the folders you name with `--agent` / `--dir`).
- It makes **no network requests**. The generated `wirehouse.html` loads nothing from the network;
  links to your code host are ordinary links you click.
- Secret values (env values, passwords, connection strings, column defaults, credentials inside a
  git remote URL) are never written to the output. Text written by the agent is scanned for
  credential-looking strings, which are removed.

## Reporting a vulnerability

Please report security issues privately, not in a public issue:
[open a private security advisory](https://github.com/creyes-git/wirehouse/security/advisories/new),
or email [github-.boaster602@passmail.com](mailto:github-.boaster602@passmail.com) if you cannot use GitHub.

Especially welcome:

- any way a secret from the scanned project ends up in `archmap.json` or `wirehouse.html`,
- any way content from a scanned repository (file names, docstrings, enrichment text) can run
  script in the generated page,
- any way the scan reads or writes outside the folders described above.

You can expect an acknowledgement within a few days and a fix or a plan within two weeks. Fixed
issues are credited in the changelog unless you ask otherwise.

## Supported versions

Security fixes go into the latest release.
