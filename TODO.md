# TODO

Known gaps and deferred work. Each entry: date, what, where, and the suggested fix.

## Create the GitHub repository and push

- **Date:** 2026-10-17
- **What:** The project has no remote yet. `creyes-git/wirehouse` still has to be created and
  `main` pushed for the first time. Until then, the README links, the CI badge, the install
  command (`pip install "git+https://github.com/creyes-git/wirehouse"`) and the live demo URL
  point at a repository that does not exist.
- **Where:** git remote `origin` (none set); links in `README.md`, `pyproject.toml`,
  `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.github/ISSUE_TEMPLATE/config.yml`,
  `wirehouse/skill/SKILL.md`.
- **Suggested fix:**
  1. Create the empty repository (no README, license or .gitignore), either by hand on
     github.com or with `gh repo create creyes-git/wirehouse --public --source . --remote origin`
     once the GitHub CLI is installed and signed in. Creating it and the first push each need
     the maintainer's explicit approval.
  2. Re-run the full history check (secrets, personal data, local paths, author emails) and the
     test suite, then `git push -u origin main`.
  3. Delete the local backup branches left by the history rewrite (`backup/*`) and
     `refs/original/`.
  4. Follow the GitHub setup checklist: CI green, About and topics, social preview, Pages
     (`main` / `docs`), Discussions, the `detection` label, private vulnerability reporting,
     a ruleset for `main`, and the `pypi` environment.
