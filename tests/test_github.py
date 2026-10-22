import json
import shutil

import yaml

from conftest import FIXTURES, run_collect

GITHUB_ENV = {"GITHUB_TOKEN": "test-token"}


def github(pool):
    return pool["github"]


def read_pool(paths):
    return json.loads(paths["out"].read_text(encoding="utf-8"))


def full_names(repos):
    return [repo["full_name"] for repo in repos]


def test_missing_github_token_fails_before_writing(cli, paths):
    result = run_collect(cli, paths, "github", env={"GITHUB_TOKEN": ""})

    assert result.returncode == 2
    assert "github.token" in result.stderr
    assert "GITHUB_TOKEN" in result.stderr
    assert not paths["out"].exists()
    assert not paths["db"].exists()


def test_new_and_active_passes_keep_one_and_two_repositories(cli, paths):
    result = run_collect(cli, paths, "github", env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    pool = read_pool(paths)
    gh = github(pool)

    assert full_names(gh["new"]) == ["acme/cell-atlas"]
    assert full_names(gh["active"]) == ["acme/scanpy-plus", "acme/spatial-hub"]
    assert full_names(gh["g6"]) == ["acme/claude-runner", "acme/codex-tool"]
    assert gh["found"] == {"new": 2, "active": 5, "g6": 3}
    assert gh["limits"] == {"new": 1, "active": 2, "g6": 2}
    assert pool["sources"]["github"] == {"status": "ok", "count": 5}
    assert pool["papers"] == []


def test_each_repo_explains_itself_with_metadata_and_readme_hits(cli, paths):
    result = run_collect(cli, paths, "github", env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    cell = gh["new"][0]
    assert cell["full_name"] == "acme/cell-atlas"
    assert cell["url"] == "https://github.com/acme/cell-atlas"
    assert cell["description"] == "Single-cell atlas toolkit"
    assert cell["positioning"] == "Single-cell atlas toolkit"
    assert cell["stars"] == 42
    assert cell["language"] == "Python"
    assert cell["created_at"] == "2026-10-20T08:00:00Z"
    assert cell["pushed_at"] == "2026-10-21T09:00:00Z"
    assert cell["topics"] == ["single-cell", "bioinformatics"]
    assert cell["group"] == "G2"
    assert cell["query"] == "topic:single-cell created:>2026-10-15 stars:>=5"
    # Single-cell is in the description; the README adds the second term.
    assert cell["tags"] == ["single-cell", "spatial transcriptomics"]
    assert cell["relevance"] == 4
    assert cell["score"] == 8
    assert cell["readme_url"] == (
        "https://raw.githubusercontent.com/acme/cell-atlas/main/README.md"
    )
    assert "G2（单细胞与空间组学）" in cell["why"]
    assert "topic:single-cell" in cell["why"]
    assert "spatial transcriptomics" in cell["why"]

    scanpy = gh["active"][0]
    assert scanpy["group"] == "G2"
    assert scanpy["tags"] == ["single-cell"]
    assert scanpy["relevance"] == 3
    # 900 stars -> round(2 * log10(900)) = 6; pushed yesterday -> +1.
    assert scanpy["score"] == 10
    assert scanpy["query"] == "topic:single-cell pushed:>2026-10-15 stars:>=30"


def test_ineligible_repositories_are_dropped(cli, paths):
    result = run_collect(cli, paths, "github", env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))
    seen = {
        repo["full_name"] for section in ("new", "active", "g6") for repo in gh[section]
    }

    # Created more than seven days ago / fewer than five stars / a fork /
    # archived: all four are filtered before ranking.
    for dropped in ("acme/too-old", "acme/few-stars", "acme/forked", "acme/archived"):
        assert dropped not in seen
    # Active needs thirty stars and a push inside the window.
    assert "acme/low-stars" not in seen
    assert "acme/stale" not in seen


def test_a_new_repo_does_not_take_an_active_slot(cli, paths):
    result = run_collect(cli, paths, "github", env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    # cell-atlas is eligible for the active pass too, and ``found`` counts it,
    # but it already appears once as a new repo.
    assert "acme/cell-atlas" not in full_names(gh["active"])
    assert gh["found"]["active"] == 5


def test_empty_passes_stay_empty_instead_of_padding(cli, paths, tmp_path):
    fixtures = tmp_path / "github-empty"
    shutil.copytree(FIXTURES / "github", fixtures)
    empty = json.dumps({"total_count": 0, "incomplete_results": False, "items": []})
    for relative in (
        "new/0.json",
        "new/1.json",
        "active/0.json",
        "active/1.json",
    ):
        (fixtures / "github" / "search" / relative).write_text(empty, encoding="utf-8")

    result = run_collect(cli, paths, "github", fixtures_dir=fixtures, env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))
    assert gh["new"] == []
    assert gh["active"] == []
    assert full_names(gh["g6"]) == ["acme/claude-runner", "acme/codex-tool"]


def test_positioning_falls_back_to_the_readme_paragraph(cli, paths, tmp_path):
    config = yaml.safe_load((FIXTURES / "github" / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["new"]["max_items"] = 2
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github",
        config=config_path,
        fixtures_dir=FIXTURES / "github",
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))
    assert full_names(gh["new"]) == ["acme/cell-atlas", "acme/spatial-kit"]

    spatial = gh["new"][1]
    assert spatial["description"] == ""
    assert spatial["positioning"] == "Spatial transcriptomics toolkit for R."
    # The only hit is in the README, so it is worth one point, not three.
    assert spatial["tags"] == ["spatial transcriptomics"]
    assert spatial["relevance"] == 1
    # 120 stars -> round(2 * log10(120)) = 4; pushed today -> +2.
    assert spatial["score"] == 7


def test_g6_queries_cover_the_claude_codex_and_dsh_ecosystems(cli, paths, tmp_path):
    config = yaml.safe_load((FIXTURES / "github" / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["g6"]["max_items"] = 3
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github",
        config=config_path,
        fixtures_dir=FIXTURES / "github",
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    # The Claude/Codex/DSH queries found three ecosystem repos; the G6 block is
    # separate from the new/active sections.
    assert gh["found"]["g6"] == 3
    assert full_names(gh["g6"]) == [
        "acme/claude-runner",
        "acme/codex-tool",
        "acme/dsh-tools",
    ]
    assert [repo["group"] for repo in gh["g6"]] == ["G6", "G6", "G6"]
    assert "deepseek harness" in gh["g6"][2]["why"]
    assert "codex" in gh["g6"][1]["tags"]
    assert full_names(gh["new"]) == ["acme/cell-atlas"]
    assert full_names(gh["active"]) == ["acme/scanpy-plus", "acme/spatial-hub"]


DISCOVERY_QUERIES = [
    # G1
    "topic:aging",
    "topic:multi-omics",
    # G2
    "topic:single-cell",
    "topic:spatial-transcriptomics",
    "topic:single-cell-analysis",
    '"spatial transcriptomics" in:name,description,readme',
    '"cell type annotation" in:name,description,readme',
    '"batch effect correction" in:name,description,readme',
    "MERFISH in:name,description,readme",
    "CITE-seq in:name,description,readme",
    '"cell-cell communication" in:name,description,readme',
    # G3
    '"single-cell foundation model" in:name,description,readme',
    "CellVQ in:name,description,readme",
    "ESM-2 in:name,description,readme",
    # G4
    "topic:gene-regulatory-network",
    '"perturbation prediction" in:name,description,readme',
    '"protein imputation" in:name,description,readme',
    # G5
    "topic:knowledge-graph",
    "topic:graph-neural-network",
    '"virtual cell" in:name,description,readme',
    "LLM single-cell in:name,description,readme",
    "GraphRAG in:name,description,readme",
]

G6_QUERIES = [
    "topic:claude-code",
    '"claude code" in:name,description,readme',
    "topic:codex",
    '"codex cli" in:name,description,readme',
    '"openai codex" in:name,description,readme',
    "topic:deepseek-harness",
    '"deepseek harness" in:name,description,readme',
    '"DSH harness" in:name,description,readme',
    "topic:ai-coding-agent",
    "topic:coding-agent",
    '"agent harness" in:name,description,readme',
    '"terminal agent" in:name,description,readme',
]


def test_default_queries_are_the_22_plus_12_decision_list(cli, paths, tmp_path):
    fixtures = tmp_path / "github-defaults"
    empty = json.dumps({"total_count": 0, "incomplete_results": False, "items": []})
    for pass_name in ("new", "active"):
        directory = fixtures / "github" / "search" / pass_name
        directory.mkdir(parents=True)
        for index in range(len(DISCOVERY_QUERIES) + len(G6_QUERIES)):
            (directory / f"{index}.json").write_text(empty, encoding="utf-8")
    releases = fixtures / "github" / "releases"
    releases.mkdir(parents=True)
    for slug in (
        "anthropics__claude-code",
        "openai__codex",
        "deepseek-ai__deepseek-harness",
    ):
        (releases / f"{slug}.json").write_text("[]\n", encoding="utf-8")

    config = {
        "timezone": "Asia/Shanghai",
        "topics": [
            {"name": f"G{number}", "label": f"Group {number}", "terms": [f"term-{number}"]}
            for number in range(1, 7)
        ],
        "sources": {"pubmed": False, "github": True},
        "github": {"token_env": "GITHUB_TOKEN"},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli, paths, "github", config=config_path, fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    assert gh["passes"]["new"]["queries"] == [
        f"{query} created:>2026-10-15 stars:>=5"
        for query in DISCOVERY_QUERIES + G6_QUERIES
    ]
    assert gh["passes"]["active"]["queries"] == [
        f"{query} pushed:>2026-10-15 stars:>=30"
        for query in DISCOVERY_QUERIES + G6_QUERIES
    ]
    assert gh["passes"]["new"]["params"] == {
        "sort": "updated",
        "order": "desc",
        "per_page": 100,
    }
    assert gh["passes"]["new"]["since"] == "2026-10-15"
    assert gh["passes"]["new"]["min_stars"] == 5
    assert gh["passes"]["active"]["min_stars"] == 30
    assert gh["passes"]["new"]["results"] == 0
    assert gh["limits"] == {"new": 1, "active": 2, "g6": 2}
    assert gh["found"] == {"new": 0, "active": 0, "g6": 0}
    assert gh["new"] == [] and gh["active"] == [] and gh["g6"] == []
    assert read_pool(paths)["sources"]["github"] == {"status": "ok", "count": 0}


def test_doctor_replays_the_recorded_github_searches(cli):
    result = cli(
        "doctor",
        "--config",
        FIXTURES / "github" / "config.yaml",
        "--fixtures",
        FIXTURES / "github",
        "--now",
        "2026-10-22T08:00:00+08:00",
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert "source github" in result.stdout
    assert "4 queries x 2 passes" in result.stdout
    assert "17 recorded items" in result.stdout
    assert "all checks passed" in result.stdout


def test_doctor_reports_a_missing_github_token(cli):
    result = cli(
        "doctor",
        "--config",
        FIXTURES / "github" / "config.yaml",
        "--fixtures",
        FIXTURES / "github",
        "--now",
        "2026-10-22T08:00:00+08:00",
        env={"GITHUB_TOKEN": ""},
    )

    assert result.returncode == 2
    assert "github.token" in result.stderr
    assert "GITHUB_TOKEN" in result.stderr


def test_a_broken_search_fixture_fails_only_the_github_source(cli, paths, tmp_path):
    fixtures = tmp_path / "github-broken"
    shutil.copytree(FIXTURES / "github", fixtures)
    (fixtures / "github" / "search" / "new" / "2.json").write_text(
        "{not json", encoding="utf-8"
    )

    result = run_collect(cli, paths, "github", fixtures_dir=fixtures, env=GITHUB_ENV)

    assert result.returncode == 1
    assert "github" in result.stderr
    assert "invalid GitHub search JSON" in result.stderr
    pool = read_pool(paths)
    assert pool["sources"]["github"]["status"] == "failed"
    assert pool["sources"]["github"]["error"]
    gh = github(pool)
    assert gh["new"] == []
    assert gh["active"] == []
    assert gh["g6"] == []
    # The failed run still records the queries and the partial item count, so
    # the failure is auditable.
    assert len(gh["passes"]["new"]["queries"]) == 4
    assert gh["passes"]["new"]["results"] == 6
    assert gh["passes"]["active"]["results"] == 0


def test_readme_budget_is_spread_across_sections(cli, paths, tmp_path):
    config = yaml.safe_load((FIXTURES / "github" / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["readme_limit"] = 2
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github",
        config=config_path,
        fixtures_dir=FIXTURES / "github",
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    # The new repo scores below several active/G6 repos, so a plain global
    # shortlist would never read its README. Each section still gets one read.
    assert gh["new"][0]["full_name"] == "acme/cell-atlas"
    assert gh["new"][0]["tags"] == ["single-cell", "spatial transcriptomics"]


def test_readme_budget_never_hides_a_section(cli, paths, tmp_path):
    config = yaml.safe_load((FIXTURES / "github" / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["readme_limit"] = 1
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github",
        config=config_path,
        fixtures_dir=FIXTURES / "github",
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    # Only one README is read (the new repo's), but every section still selects
    # from all of its eligible repositories.
    assert full_names(gh["new"]) == ["acme/cell-atlas"]
    assert gh["new"][0]["tags"] == ["single-cell", "spatial transcriptomics"]
    assert full_names(gh["active"]) == ["acme/scanpy-plus", "acme/spatial-hub"]
    assert full_names(gh["g6"]) == ["acme/claude-runner", "acme/codex-tool"]


def test_a_repo_found_by_a_g6_query_appears_only_in_the_g6_block(cli, paths, tmp_path):
    fixtures = tmp_path / "github-overlap"
    shutil.copytree(FIXTURES / "github", fixtures)
    overlap = {
        "full_name": "acme/single-cell-harness",
        "name": "single-cell-harness",
        "owner": {"login": "acme"},
        "html_url": "https://github.com/acme/single-cell-harness",
        "description": "Single-cell agent harness",
        "stargazers_count": 500,
        "language": "Python",
        "created_at": "2026-10-20T08:00:00Z",
        "pushed_at": "2026-10-22T08:00:00Z",
        "updated_at": "2026-10-22T08:00:00Z",
        "topics": ["single-cell", "claude-code"],
        "fork": False,
        "archived": False,
        "default_branch": "main",
    }
    for relative in ("new/0.json", "new/2.json"):
        path = fixtures / "github" / "search" / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["items"].append(overlap)
        payload["total_count"] = len(payload["items"])
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = run_collect(cli, paths, "github", fixtures_dir=fixtures, env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    # Both the G2 query and the G6 query returned it; the G6 provenance wins and
    # the repository is not repeated in the new or active section.
    assert "acme/single-cell-harness" not in full_names(gh["new"])
    assert "acme/single-cell-harness" not in full_names(gh["active"])
    assert full_names(gh["g6"]) == ["acme/claude-runner", "acme/single-cell-harness"]
    harness = gh["g6"][1]
    assert harness["group"] == "G6"
    assert "topic:claude-code" in harness["why"]
    assert gh["found"]["g6"] == 4


def test_positioning_falls_back_when_there_is_no_description_or_readme(
    cli, paths, tmp_path
):
    fixtures = tmp_path / "github-no-positioning"
    shutil.copytree(FIXTURES / "github", fixtures)
    (fixtures / "github" / "readme" / "acme__spatial-kit.md").unlink()
    config = yaml.safe_load((FIXTURES / "github" / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["new"]["max_items"] = 2
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github",
        config=config_path,
        fixtures_dir=fixtures,
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    assert full_names(gh["new"]) == ["acme/cell-atlas", "acme/spatial-kit"]
    spatial = gh["new"][1]
    assert spatial["positioning"] == "acme/spatial-kit（无描述）"
    assert spatial["description"] == ""
    assert spatial["tags"] == []


def test_a_g6_hit_does_not_consume_its_discovery_section_readme(
    cli, paths, tmp_path
):
    fixtures = tmp_path / "github-overlap-budget"
    shutil.copytree(FIXTURES / "github", fixtures)
    overlap = {
        "full_name": "acme/single-cell-harness",
        "name": "single-cell-harness",
        "owner": {"login": "acme"},
        "html_url": "https://github.com/acme/single-cell-harness",
        "description": "Single-cell agent harness",
        "stargazers_count": 500,
        "language": "Python",
        "created_at": "2026-10-20T08:00:00Z",
        "pushed_at": "2026-10-22T08:00:00Z",
        "updated_at": "2026-10-22T08:00:00Z",
        "topics": ["single-cell", "claude-code"],
        "fork": False,
        "archived": False,
        "default_branch": "main",
    }
    for relative in ("new/0.json", "new/2.json"):
        path = fixtures / "github" / "search" / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["items"].append(overlap)
        payload["total_count"] = len(payload["items"])
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    config = yaml.safe_load((FIXTURES / "github" / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["readme_limit"] = 1
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github",
        config=config_path,
        fixtures_dir=fixtures,
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    gh = github(read_pool(paths))

    # The G6-only repo is not eligible for a new slot, so the single README
    # read goes to the best actual new repo.
    cell = gh["new"][0]
    assert cell["full_name"] == "acme/cell-atlas"
    assert cell["tags"] == ["single-cell", "spatial transcriptomics"]
    assert full_names(gh["g6"]) == ["acme/claude-runner", "acme/single-cell-harness"]
    # found is counted before the cross-section exclusion, so the G6 repo still
    # shows up in the new-pass count.
    assert gh["found"]["new"] == 3
