# Coding standards

Read by the code reviewer, not the implementation agent. Anything that can be a deterministic check belongs in `scripts/check.sh`; this file covers the judgement calls a reviewer should apply.

## Source adapters

- A source module exports `NAME`, `collect(config, fixtures_root, now)`, and `check(config, fixtures_root)`.
- `collect` returns a `SourceResult`; one failed source never aborts the others.
- Fixture layout is `<fixtures>/<source>/<recorded-response>`. Use `base.read_or_fetch` so `--fixtures` never touches the network.
- A fixture must mirror the real response shape, including separators. bioRxiv authors, for example, are semicolon-separated `Last, First`.

## Candidate pool

- `attach_topic` owns group, tags, score, `abstract_missing`, and the preprint marker.
- Tag order: matched terms, then `预印本` when `is_preprint`, then `无摘要` when the abstract is empty.
- `is_preprint` is true only when every merged version is a preprint.
- Dedupe key priority: DOI > PMID > arXiv ID > normalized-title-plus-year.

## Config

- Validate before any network request; raise `ConfigError(field, message)` with a dotted field.
- An enabled source needs its `lookback` entry. arXiv additionally requires `arxiv.categories` and a four-day minimum.

## Tests

- Test at the CLI seam: subprocess `collect` / `doctor`, asserting exit code, stderr, and output files.
- Tests stay offline and deterministic: pass `--fixtures` and a fixed `--now`; no sleeps or wall-clock dependencies.
- Add a test whenever a documented ordering, marker, default, or switch changes.

## Docs

- A doc claim about ordering, labels, or defaults must match a test or config fixture.
- Update `README.md`, `config.example.yaml`, and the ADR when a source or config contract changes.

Review process: `docs/agents/code-review.md`. Checks: `scripts/check.sh`.
