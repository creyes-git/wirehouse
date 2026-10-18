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

## Viewer tests can time out on a slow machine

- **Date:** 2026-10-18
- **What:** `tests/test_viewer.py` opens a new page per test and the older tests never close theirs, so
  every WebGL page keeps rendering. On this machine a full run sometimes hit Playwright's 30 s load
  timeout in a later test, then passed on a rerun.
- **Where:** `tests/test_viewer.py`, the tests before `test_a_floor_plan_link_opens_on_a_fresh_page`.
- **Suggested fix:** close each page at the end of its test (or yield pages from a fixture that closes
  them), as the newer tests do.
