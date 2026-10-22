# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading
- Comments describe behaviour, decisions, and deviations. Counts and file listings belong to the tools that report them (`pytest -q`, `git show --stat`); a number written into a Comment goes stale as soon as the suite grows.
- A ticket that changes the JSON payload has a `## Contract` section: the keys it adds or changes and where they sit, the existing keys whose meaning must not change, the empty/missing behavior, and the behavior when the feature is not configured.

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Not used by this project. If a future effort needs `/wayfinder`, use:

- **Map**: `.scratch/<effort>/map.md`
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`
- **Blocking**: a `Blocked by: NN, NN` line near the top
- **Claim / resolve**: `Status: claimed` / `Status: resolved`, with the answer under `## Answer`
