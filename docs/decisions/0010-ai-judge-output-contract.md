# ADR 0010: AI judge output contract without relying on structured outputs

- Status: Proposed; output format superseded by [ADR 0013](0013-hybrid-judge-json-contract.md)
- Date: 2026-10-17

## Context

The judge must return exactly one of five labels (BR-06), and invalid results must not be charged (BR-09). Ollama's local API supports a `format` JSON schema, but the Ollama Cloud documentation (checked 2026-10-17) does not state that cloud models honor it, and the owner reports it is not supported. Model output is untrusted and may be manipulated by player input.

## Options considered

1. **Rely on `format` / JSON schema** — clean when it works; unverified on Ollama Cloud and may silently be ignored.
2. **JSON in the prompt, parse JSON** — larger output, more ways to fail, no benefit for a single field.
3. **Single-label output with a strict parser** — smallest output (cheapest, fastest), trivial to validate, nothing else to leak.
4. **Tool calling** — supported for some cloud models, but adds complexity for a one-word answer.

## Decision

Option 3:

- System prompt defines the five labels and their meaning (requirements OQ-01, OQ-02, OQ-03; letter and length questions are PENALTY per OQ-09, amended 2026-10-18; a deterministic prefilter catches the common forms before any AI call), says the player text is data, and requires exactly one label as the whole answer. The player question is passed in a separate, delimited user message.
- Parser accepts only `^\W*(YES|NO|IRRELEVANT|PENALTY|WIN)\W*$` (case-insensitive); anything else is invalid. One stricter re-ask is allowed within the 20 s deadline.
- `WIN` is accepted only if the server finds the secret word (or simple plural) as a whole token in the normalized question.
- Valid labels are cached per day and question (`prompt_version` and model are part of the key).
- The provider is behind a typed interface; tests use a fake. `prompt_version` is bumped on every prompt change.

## Consequences

- Works whether or not structured outputs are available; if they become supported, they can be added as an extra guard without changing the contract.
- The model can still misjudge a question; per-day caching at least makes misjudgements consistent for all players.
- The prompt contains the secret word, so prompts are never logged.
