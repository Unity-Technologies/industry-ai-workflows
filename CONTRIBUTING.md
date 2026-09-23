# Contributing

Thanks for your interest in Industry AI Workflows.

- **Issues and feature requests are welcome** — please use the GitHub issue
  tracker and include your OS, Python version, and the relevant log output
  (each plugin keeps its own setup log in its data directory as
  `bootstrap.log` — say which plugin).
- **Dependency PRs opened against this repository can't be merged here.**
  The branch is regenerated on each release (see below), so a commit landed on
  it would be discarded. Security reports are still valuable — we apply the fix
  upstream and the next release carries it.
- **Please open an issue before a pull request.** Releases here are published
  as whole snapshots rather than merged commit by commit, so a pull request
  raised without discussion is likely to be superseded rather than merged.
  Describing the change in an issue first means we can tell you whether and how
  it can land — and credit it properly when it does.

## How releases work

This repository is a published snapshot. Each release replaces its entire
history with one commit containing the tree as it ships, minted from a
development repository that is not public. That is why there are no merge
commits, no feature branches, and no development history here — and why the
changelog starts at the current release.

Practically, for anyone reading the code: what you see is exactly what the
plugins run. Nothing is generated at install time beyond the Python
environments each plugin builds for its own server.
