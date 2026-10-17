# Architecture Decision Records

An ADR records one significant decision: its context, the choice, and the consequences. ADRs are immutable once accepted — to change a decision, add a new ADR that supersedes the old one and update the old one's status.

## When to write one

- Choosing or replacing a framework, service, datastore, or hosting target
- Changing a security boundary, data model, or public API contract
- Accepting a known trade-off or limitation

## Process

1. Copy `template.md` to `NNNN-short-title.md` (next number, zero-padded).
2. Status `Proposed` in the PR; set to `Accepted` when the PR is merged.
3. Link the ADR from `docs/progress.md` and, if relevant, `docs/architecture.md`.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-claude-code-tooling.md) | Claude Code tooling for the repository | Accepted |
| [0002](0002-engineering-conventions.md) | Engineering conventions and workflow | Proposed |
