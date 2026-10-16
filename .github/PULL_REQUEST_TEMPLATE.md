## What and why

<!-- One topic per pull request. Link the issue if there is one: Fixes #123 -->

## How I checked it

- [ ] `python -m pytest` passes (new behaviour has a test)
- [ ] For viewer changes: `node --check wirehouse/render/app.js` and `python -m pytest tests/test_viewer.py`, plus a screenshot or clip below
- [ ] Tried it on a real project: `wirehouse build <path> --open`
- [ ] `CHANGELOG.md` updated under **Unreleased**

## Ground rules

- [ ] Nothing new is drawn or counted without a recorded connection or checked evidence
- [ ] No secret values can reach `archmap.json` or the HTML
- [ ] The page still loads nothing from the network
