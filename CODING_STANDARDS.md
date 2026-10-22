# Coding standards

Read by the code reviewer, not the implementation agent. Anything that can be a deterministic check belongs in `scripts/check.sh`; this file covers the judgement calls a reviewer should apply.

## Source adapters

- A source module exports `NAME`, `collect(config, fixtures_root, now)`, and `check(config, fixtures_root)`.
- `collect` returns a `SourceResult`; one failed source never aborts the others.
- Fixture layout is `<fixtures>/<source>/<recorded-response>`. Use `base.read_or_fetch` so `--fixtures` never touches the network.
- A fixture must mirror the real response shape, including separators. bioRxiv authors, for example, are semicolon-separated `Last, First`.

## Candidate pool

- `attach_topic` owns group, tags, `relevance`, `abstract_missing`, and the preprint marker.
- `ranking.select_candidates` sets `score` (relevance plus the freshness bonus), orders the pool (score, date, id), reserves each non-empty group's best paper, and enforces each group's `max_items` plus `pool.max_items`. Config validation keeps `pool.max_items` at or above the topic count so every group's reservation fits. A short pool is never padded.
- Tag order: matched terms, then `预印本` when `is_preprint`, then `无摘要` when the abstract is empty.
- `is_preprint` is true only when every merged version is a preprint.
- Dedupe key priority: DOI > PMID > arXiv ID > normalized-title-plus-year.

## GitHub discovery

- `academic_digest/github.py` exports `NAME`, `discover(config, fixtures_root, now)`, and `check(config, fixtures_root)`. It is deliberately outside the paper-source registry: a repository never enters `papers`.
- The token comes from `github.token_env` (default `GITHUB_TOKEN`). Config validation raises `github.token` before any request when it is empty, and the token never appears in output, logs, or the digest.
- `github.queries` maps a topic name to server-side queries; the default is the 22-query G1–G5 recipe. `github.g6_queries` feeds the G6 block; the default is the 12-query Claude Code/Codex/DSH list. Each query runs in both passes as `<query> created:>{since} stars:>={min_stars}` and `<query> pushed:>{since} stars:>={min_stars}`, with `sort=updated`, `order=desc`, and only the first page of 100 — `sort=updated` reshuffles while paging.
- Eligibility: new needs `created > since` and stars at or above `github.new.min_stars`; active needs `pushed > since` and stars at or above `github.active.min_stars`; forks and archived repositories are dropped. A repository's group comes from the query that returned it, so it is never dropped for matching no keyword.
- Scoring: `relevance` is 3 per group term in the full name, description, or topics, plus 1 per group term found only in the README. `score` adds `round(2 * log10(stars))` and push recency (today 2, yesterday 1). Ordering is score, stars, pushed-at, full name.
- READMEs come from `raw.githubusercontent.com`, which costs no API quota. Each section offers its best `max_items + README_SLACK` (3) candidates and the `github.readme_limit` budget (default 20) is shared round-robin, so a high-star active repository cannot starve the new or G6 sections of README evidence. A candidate outside the budget still competes for a slot, just without the README bonus. A missing README is empty, not a source failure. Search requests are serial with a two-second gap and carry a User-Agent and the token.
- Caps come from `github.new.max_items` (default 1), `github.active.max_items` (2), and `github.g6.max_items` (2). A repository selected as new never takes an active slot; a repository returned by a G6 query appears only in the G6 block, with G6 provenance even when a discovery query also returned it; a short section is never padded. `found` counts eligible repositories before the caps and before the cross-section exclusions. A failed run keeps `github.passes` (queries and partial item counts) so the attempt is auditable.
- Fixtures: `github/search/{new,active}/{query-index}.json` follows query order, so query construction is observable in `github.passes.<pass>.queries`; READMEs are optional files at `github/readme/{owner}__{repo}.md`.

## Full text

- Resolution order is fixed: Europe PMC OA XML, arXiv HTML then PDF, the bioRxiv/medRxiv/Research Square preprint PDF, then Unpaywall's best OA location. Each source records one `Attempt`; internal fallbacks (HTML→PDF, multiple OA candidates) collapse into that source's entry. The overall result is `no_oa` with a reason and exit code 0, never an exception.
- `fulltext.unpaywall.email` is optional: without it the Unpaywall attempt is skipped and the other sources still run. The email must not appear in the digest output; a live Unpaywall failure is sanitized because the request URL carries `email=...`.
- Extraction keeps methods/results/limitations only, deduplicated and capped at 4/3/4 paragraphs and 4000/3000/2000 characters, truncated at a sentence boundary in the second half of the budget when one exists, otherwise at a word boundary. `length` is the sum of the kept paragraphs; the two truncation fixtures pin the paragraph and character caps. When no explicit Limitations section exists, only Discussion/Conclusion prose may supply an author limitation; Methods/Results prose is not promoted by keyword.
- Every Europe PMC search hit must carry the requested DOI before its PMC id is used; a DOI-less neighbouring record is skipped.
- Fixture layout mirrors the source: `europepmc/doi-search.json` + `fulltext.xml`, `arxiv/fulltext.html|pdf`, `<preprint>/fulltext.pdf`, `unpaywall/location.json` + `fulltext.pdf|html`. Binary fixtures go through `base.read_or_fetch_bytes`; `--fixtures` never touches the network.

## Config

- Validate before any network request; raise `ConfigError(field, message)` with a dotted field.
- An enabled source needs its `lookback` entry, except GitHub: it carries its own `github.new.days` / `github.active.days` windows. A missing `lookback` block means "no lookback-driven sources", so enabling one of them fails with `lookback.<source>` rather than a bare mapping error. arXiv additionally requires `arxiv.categories` and a four-day minimum.

## Tests

- Test at the CLI seam: subprocess `collect` / `fulltext` / `doctor`, asserting exit code, stderr, and output files.
- Tests stay offline and deterministic: pass `--fixtures` and a fixed `--now`; no sleeps or wall-clock dependencies. `fulltext` has no date logic, so its tests rely on `--fixtures` alone.
- Add a test whenever a documented ordering, marker, default, or switch changes.

## Docs

- A doc claim about ordering, labels, or defaults must match a test or config fixture.
- Update `README.md`, `config.example.yaml`, and the ADR when a source or config contract changes.

Review process: `docs/agents/code-review.md`. Checks: `scripts/check.sh`.
