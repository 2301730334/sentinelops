# Git workflow

## Branches

| Branch | Purpose | Rules |
|---|---|---|
| `main` | Stable, releasable code. Every merge is tagged (`v0.1.0`, …) | Only merges from `develop` (or `hotfix/*`). Protect it on GitHub: require a PR and passing CI |
| `develop` | Integration branch. Features meet here first | Only merges from short-lived branches |
| `feature/<name>` | One feature per branch, e.g. `feature/rest-api` | Branch from `develop`, merge back with `--no-ff` |
| `fix/<name>` | Bug fixes found during integration | Same as feature |
| `docs/<name>` | Documentation-only changes | Same as feature |

Merges use `--no-ff`, so every feature stays visible as its own loop in
`git log --graph`.

```text
main     ──●──────────────────────────────────────────────●  v0.1.0
            \                                            /
develop      ●──●──────●──────●──────●────────●──●──●───●
                 \    / \    / \    / \      / \   /
feature/...       ●──●   ●──●   ●──●   ●──●─●   ●─●   ...
```

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`.

| Type | Used for |
|---|---|
| `feat` | New functionality |
| `fix` | Bug fix |
| `test` | Adding or changing tests |
| `docs` | Documentation |
| `chore` | Tooling, dependencies, repo housekeeping |
| `perf` | Performance improvement |
| `refactor` | Code change with no behaviour change |
| `ci` | Pipeline changes (Phase 2+) |

Keep commits small, and make sure the test suite passes at every commit.

## Day-to-day flow (2-person team)

```bash
git switch develop && git pull
git switch -c feature/<name>
# ...work, commit in small steps...
pytest
git push -u origin feature/<name>
# open a Pull Request feature/<name> -> develop on GitHub; teammate reviews; merge
```

Release:

```bash
git switch main && git merge --no-ff develop -m "chore(release): v0.2.0"
git tag -a v0.2.0 -m "Phase 2: CI + containers"
git push origin main --tags
```

## Recorded merge conflict (Phase 1)

`feature/rest-api` and `feature/observability` both branched from `develop`
after `feature/scan-crud` was merged. Each one registered a new blueprint on
the same line of `register_blueprints()` in `app/__init__.py`:

```text
    app.register_blueprint(scans_bp)
<<<<<<< HEAD
    app.register_blueprint(api_bp)
=======
    app.register_blueprint(ops_bp)
>>>>>>> feature/observability
```

`feature/rest-api` was merged first. Merging `feature/observability` then
conflicted. The resolution keeps both registrations (and both imports), runs the
full test suite, and commits the merge with an explanatory message:

```bash
git switch develop
git merge --no-ff feature/observability       # CONFLICT (content): app/__init__.py
# edit the file: keep api_bp AND ops_bp, remove the markers
pytest                                        # all green
git add app/__init__.py
git commit                                    # "Merge branch 'feature/observability' into develop" + resolution note
```

To see it in the history:

```bash
git log --oneline --graph --all
git log --merges --grep "Resolve conflict" --format='%h %s%n%b'
```
