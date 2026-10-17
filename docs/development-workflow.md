# Development Workflow

How a task moves from idea to `main`. Roles: the **owner** decides scope, reviews, pushes, and merges; **Claude** plans, implements, tests, and explains on a local branch.

## 1. Task loop

1. **Start** — fresh Claude session on the repo. Claude loads `CLAUDE.md` automatically and reads the docs it lists.
2. **Sync** — `git checkout main && git pull`, then create a branch: `git checkout -b feat/<short-name>`.
3. **Plan** — for non-trivial work Claude proposes a plan (files, tests, risks). The owner approves or adjusts the scope.
4. **Implement** — only the approved scope. Relevant project skill is used for review (game integrity, AI judge, deployment).
5. **Verify** — run lint, type check, and tests; report exact commands and results.
6. **Review** — `git diff` reviewed by Claude (and `pr-review-toolkit` agents for larger changes), then by the owner.
7. **Document** — update `docs/progress.md`; ADR / architecture if a decision or structure changed.
8. **Commit** — Conventional Commit, owner as sole author, no AI trailers.
9. **Push and PR** — done by the owner.
10. **Merge** — after CI is green and the owner approves; delete the branch.

## 2. Starting a session (prompt template)

```
Task: <one sentence>
Scope: <what is in / out>
Branch: feat/<name>
Read CLAUDE.md and the docs it lists, inspect git status, then propose a plan before editing.
```

## 3. Commit

```bash
git status                 # what changed
git diff                   # review unstaged changes
git add <files>            # stage deliberately; avoid `git add .` blindly
git diff --staged          # review exactly what will be committed
git commit                 # message: type(scope): summary
```

## 4. Push and Pull Request (owner)

```bash
git push -u origin <branch>
```

Then open a PR on GitHub from `<branch>` into `main`:

- Title = the main commit summary.
- Description: what changed, why, how it was tested, risks, docs updated.
- Wait for CI; address review comments with new commits on the same branch.
- Merge with **Squash and merge**, then delete the remote branch and locally:
  `git checkout main && git pull && git branch -d <branch>`.

## 5. Definition of done

- [ ] Scope matches the approved plan
- [ ] Lint, type check, and tests run locally and in CI
- [ ] No secrets, debug code, or unrelated changes in the diff
- [ ] Docs and `progress.md` updated
- [ ] Owner reviewed the diff
