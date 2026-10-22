import json
import shutil

import yaml

from conftest import FIXTURES, run_collect

GITHUB_ENV = {"GITHUB_TOKEN": "test-token"}
RELEASES = FIXTURES / "github-releases"

OFFICIAL_REPOS = (
    "anthropics/claude-code",
    "openai/codex",
    "deepseek-ai/deepseek-harness",
)


def read_pool(paths):
    return json.loads(paths["out"].read_text(encoding="utf-8"))


def releases(pool):
    return pool["github"]["releases"]


def tags(items):
    return [f'{item["repo"]} {item["tag"]}' for item in items]


def test_starred_releases_keep_at_most_two_entries(cli, paths):
    result = run_collect(cli, paths, "github-releases", env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    payload = read_pool(paths)
    block = releases(payload)

    assert tags(block["starred"]) == [
        "acme/aging-atlas v0.3.0",
        "acme/multi-omics-tools v1.4.0",
    ]
    # Four starred repositories have a release inside the seven-day window;
    # only the two newest are shown, and each repository appears once.
    assert block["found"]["starred"] == 4
    assert block["limits"]["starred"] == 2
    assert block["days"] == 7
    assert block["since"] == "2026-10-15"

    aging = block["starred"][0]
    assert aging["repo"] == "acme/aging-atlas"
    assert aging["tag"] == "v0.3.0"
    assert aging["name"] == "Aging Atlas 0.3.0"
    assert aging["date"] == "2026-10-22"
    assert "- Faster cell-type annotation" in aging["highlights"]
    assert aging["url"] == (
        "https://github.com/acme/aging-atlas/releases/tag/v0.3.0"
    )
    assert aging["prerelease"] is False
    assert aging["group"] == "G1"
    # Two G1 terms hit the description/topics; the release notes add nothing.
    assert aging["relevance"] == 6

    multi = block["starred"][1]
    assert multi["date"] == "2026-10-20"
    assert multi["highlights"] == "Adds proteomics alignment.\n\nFixes a memory leak."
    assert multi["group"] == "G1"
    assert multi["relevance"] == 3
    assert multi["prerelease"] is True

    # A release older than the window and a repository with no release never
    # reach the block.
    shown = {item["repo"] for item in block["starred"]}
    assert "acme/old-release" not in shown
    assert "acme/no-release" not in shown
    assert len(shown) == len(block["starred"])
    # The source count still counts repositories, not releases.
    assert payload["sources"]["github"] == {"status": "ok", "count": 0}


def test_official_releases_fill_the_g6_data(cli, paths):
    result = run_collect(cli, paths, "github-releases", env=GITHUB_ENV)

    assert result.returncode == 0, result.stderr
    payload = read_pool(paths)
    official = payload["github"]["g6_releases"]

    assert tags(official) == [
        "anthropics/claude-code v2.0.0",
        "openai/codex v0.9.0",
        "deepseek-ai/deepseek-harness v1.2.0",
    ]
    assert [item["date"] for item in official] == [
        "2026-10-21",
        "2026-10-20",
        "2026-10-19",
    ]
    assert all(item["group"] == "G6" for item in official)
    claude = official[0]
    assert claude["highlights"] == "Adds /compact and faster startup."
    assert claude["url"] == (
        "https://github.com/anthropics/claude-code/releases/tag/v2.0.0"
    )

    # Claude Code and Codex are also starred, but each release appears once:
    # official repositories belong to the G6 data, not the starred section.
    block = releases(payload)
    starred_repos = {item["repo"] for item in block["starred"]}
    assert not starred_repos.intersection(OFFICIAL_REPOS)
    assert "official" not in block
    assert payload["github"]["g6"] == []
    assert payload["sources"]["github"] == {"status": "ok", "count": 0}


def test_an_official_repo_without_a_new_release_is_absent(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-official"
    shutil.copytree(RELEASES, fixtures)
    for slug in ("openai__codex", "deepseek-ai__deepseek-harness"):
        (fixtures / "github" / "releases" / f"{slug}.json").write_text(
            "[]\n", encoding="utf-8"
        )

    result = run_collect(
        cli, paths, "github-releases", fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 0, result.stderr
    payload = read_pool(paths)
    assert tags(payload["github"]["g6_releases"]) == [
        "anthropics/claude-code v2.0.0"
    ]


def test_no_release_updates_omit_the_release_block(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-none"
    shutil.copytree(RELEASES, fixtures)
    for path in (fixtures / "github" / "releases").glob("*.json"):
        path.write_text("[]\n", encoding="utf-8")

    result = run_collect(
        cli, paths, "github-releases", fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 0, result.stderr
    payload = read_pool(paths)
    # No update means no release blocks at all, not empty ones.
    assert "releases" not in payload["github"]
    assert "g6_releases" not in payload["github"]
    assert payload["sources"]["github"] == {"status": "ok", "count": 0}


def test_doctor_replays_the_recorded_release_feeds(cli):
    result = cli(
        "doctor",
        "--config",
        RELEASES / "config.yaml",
        "--fixtures",
        RELEASES,
        "--now",
        "2026-10-22T08:00:00+08:00",
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert "source github" in result.stdout
    # Eight starred repos plus the three official ones, with Claude Code and
    # Codex shared by both lists, means nine feeds; only one is empty.
    assert "releases: 9 feeds, 9 recorded releases" in result.stdout


def test_same_day_releases_are_ordered_by_relevance(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-relevance"
    shutil.copytree(RELEASES, fixtures)
    path = fixtures / "github" / "releases" / "acme__older-release-only.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[0]["published_at"] = "2026-10-20T02:00:00Z"
    payload[0]["body"] = "Adds multi-omics support."
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = run_collect(
        cli, paths, "github-releases", fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 0, result.stderr
    block = releases(read_pool(paths))
    # Both releases are dated 2026-10-20; the older-release-only notes match one
    # extra term ("multi-omics"), so it wins the second slot over the repository
    # whose only hit is its metadata.
    assert tags(block["starred"]) == [
        "acme/aging-atlas v0.3.0",
        "acme/older-release-only v0.9.0",
    ]
    assert block["starred"][1]["relevance"] == 4
    assert block["found"]["starred"] == 4


def test_the_release_window_includes_its_first_day(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-boundary"
    shutil.copytree(RELEASES, fixtures)
    path = fixtures / "github" / "releases" / "acme__old-release.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[0]["published_at"] = "2026-10-15T02:00:00Z"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    config = yaml.safe_load((RELEASES / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["releases"]["max_items"] = 5
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github-releases",
        config=config_path,
        fixtures_dir=fixtures,
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    block = releases(read_pool(paths))
    # since is 2026-10-15, and a release published on that day still counts.
    assert block["since"] == "2026-10-15"
    boundary = [item for item in block["starred"] if item["repo"] == "acme/old-release"]
    assert boundary and boundary[0]["date"] == "2026-10-15"
    assert block["found"]["starred"] == 5


def test_draft_and_undated_releases_are_ignored(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-ineligible"
    shutil.copytree(RELEASES, fixtures)
    path = fixtures / "github" / "releases" / "acme__multi-omics-tools.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.append(
        {
            "tag_name": "v1.5.0-draft",
            "name": "Draft 1.5.0",
            "body": "Draft notes.",
            "published_at": "2026-10-22T02:00:00Z",
            "created_at": "2026-10-22T02:00:00Z",
            "html_url": "https://github.com/acme/multi-omics-tools/releases/tag/v1.5.0-draft",
            "draft": True,
            "prerelease": False,
        }
    )
    payload.append(
        {
            "tag_name": "v1.6.0",
            "name": "Undated 1.6.0",
            "body": "No publish time.",
            "created_at": "2026-10-22T02:00:00Z",
            "html_url": "https://github.com/acme/multi-omics-tools/releases/tag/v1.6.0",
            "draft": False,
            "prerelease": False,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = run_collect(
        cli, paths, "github-releases", fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 0, result.stderr
    block = releases(read_pool(paths))
    # A draft has no publication, and a missing published_at is not replaced by
    # created_at, so both entries stay out even though they are newer.
    assert tags(block["starred"]) == [
        "acme/aging-atlas v0.3.0",
        "acme/multi-omics-tools v1.4.0",
    ]
    assert {item["tag"] for item in block["starred"]}.isdisjoint(
        {"v1.5.0-draft", "v1.6.0"}
    )
    assert block["found"]["starred"] == 4


def test_the_latest_release_of_a_day_wins(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-same-day"
    shutil.copytree(RELEASES, fixtures)
    path = fixtures / "github" / "releases" / "acme__multi-omics-tools.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.append(
        {
            "tag_name": "v1.9.0",
            "name": "Multi-omics tools 1.9.0",
            "body": "Later same-day fix.",
            "published_at": "2026-10-20T08:00:00Z",
            "created_at": "2026-10-20T08:00:00Z",
            "html_url": "https://github.com/acme/multi-omics-tools/releases/tag/v1.9.0",
            "draft": False,
            "prerelease": False,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = run_collect(
        cli, paths, "github-releases", fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 0, result.stderr
    block = releases(read_pool(paths))
    # Both releases share the local date 2026-10-20; the later timestamp wins.
    assert tags(block["starred"]) == [
        "acme/aging-atlas v0.3.0",
        "acme/multi-omics-tools v1.9.0",
    ]
    assert block["starred"][1]["date"] == "2026-10-20"


def test_highlights_are_capped_inside_the_limit(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-long-notes"
    shutil.copytree(RELEASES, fixtures)
    aging_path = fixtures / "github" / "releases" / "acme__aging-atlas.json"
    aging = json.loads(aging_path.read_text(encoding="utf-8"))
    aging[0]["body"] = "a" * 600 + "\n\n" + "b" * 600
    aging_path.write_text(json.dumps(aging, ensure_ascii=False), encoding="utf-8")
    multi_path = fixtures / "github" / "releases" / "acme__multi-omics-tools.json"
    multi = json.loads(multi_path.read_text(encoding="utf-8"))
    multi[0]["body"] = "c" * 1500
    multi_path.write_text(json.dumps(multi, ensure_ascii=False), encoding="utf-8")

    result = run_collect(
        cli, paths, "github-releases", fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 0, result.stderr
    starred = releases(read_pool(paths))["starred"]
    # A blank line in the second half wins as the cut point.
    assert starred[0]["highlights"] == "a" * 600 + "…"
    # Without a line break the hard cap includes the ellipsis.
    assert len(starred[1]["highlights"]) == 1000
    assert starred[1]["highlights"].endswith("…")


def test_a_config_without_release_tracking_omits_the_block(cli, paths, tmp_path):
    fixtures = tmp_path / "github-no-releases"
    for pass_name in ("new", "active"):
        directory = fixtures / "github" / "search" / pass_name
        directory.mkdir(parents=True)
        (directory / "0.json").write_text(
            json.dumps(
                {"total_count": 0, "incomplete_results": False, "items": []}
            ),
            encoding="utf-8",
        )
    config = {
        "timezone": "Asia/Shanghai",
        "topics": [{"name": "G2", "label": "单细胞", "terms": ["single-cell"]}],
        "sources": {"pubmed": False, "github": True},
        "github": {
            "token_env": "GITHUB_TOKEN",
            "queries": {"G2": ["topic:single-cell"]},
            "g6_queries": [],
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github-no-releases",
        config=config_path,
        fixtures_dir=fixtures,
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    payload = read_pool(paths)
    # No G6 topic means no official list, and no user means no starred list, so
    # the release sections are neither requested nor emitted.
    assert "releases" not in payload["github"]
    assert "g6_releases" not in payload["github"]
    assert payload["sources"]["github"] == {"status": "ok", "count": 0}


def test_a_broken_release_feed_fails_only_the_github_source(cli, paths, tmp_path):
    fixtures = tmp_path / "github-releases-broken"
    shutil.copytree(RELEASES, fixtures)
    (fixtures / "github" / "releases" / "acme__no-release.json").write_text(
        "{not json", encoding="utf-8"
    )

    result = run_collect(
        cli, paths, "github-releases", fixtures_dir=fixtures, env=GITHUB_ENV
    )

    assert result.returncode == 1
    assert "github" in result.stderr
    assert "invalid GitHub releases" in result.stderr
    payload = read_pool(paths)
    assert payload["sources"]["github"]["status"] == "failed"
    assert payload["sources"]["github"]["error"]
    assert payload["github"]["new"] == []
    assert payload["github"]["active"] == []
    assert payload["github"]["g6"] == []
    assert "releases" not in payload["github"]
    assert "g6_releases" not in payload["github"]


def test_release_defaults_are_seven_days_and_two_starred_entries(
    cli, paths, tmp_path
):
    config = yaml.safe_load((RELEASES / "config.yaml").read_text(encoding="utf-8"))
    config["github"].pop("releases")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github-releases",
        config=config_path,
        fixtures_dir=RELEASES,
        env=GITHUB_ENV,
    )

    assert result.returncode == 0, result.stderr
    block = releases(read_pool(paths))
    # The defaults are seven days and two starred releases; official is one
    # release per configured official repository.
    assert block["days"] == 7
    assert block["since"] == "2026-10-15"
    assert block["limits"] == {"starred": 2}
    assert len(block["starred"]) == 2
    assert len(read_pool(paths)["github"]["g6_releases"]) == 3


def test_invalid_release_window_values_fail_before_collecting(cli, paths, tmp_path):
    for index, (window, field) in enumerate(
        (
            ({"days": 0}, "github.releases.days"),
            ({"max_items": -1}, "github.releases.max_items"),
        )
    ):
        config = yaml.safe_load((RELEASES / "config.yaml").read_text(encoding="utf-8"))
        config["github"]["releases"] = window
        config_path = tmp_path / f"config-{index}.yaml"
        config_path.write_text(
            yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
        )

        result = run_collect(
            cli,
            paths,
            "github-releases",
            config=config_path,
            fixtures_dir=RELEASES,
            env=GITHUB_ENV,
        )

        assert result.returncode == 2
        assert field in result.stderr
        assert not paths["out"].exists()
        assert not paths["db"].exists()


def test_an_invalid_official_repo_slug_fails_before_collecting(cli, paths, tmp_path):
    config = yaml.safe_load((RELEASES / "config.yaml").read_text(encoding="utf-8"))
    config["github"]["official"] = ["anthropics/claude-code", "not-a-repo"]
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = run_collect(
        cli,
        paths,
        "github-releases",
        config=config_path,
        fixtures_dir=RELEASES,
        env=GITHUB_ENV,
    )

    assert result.returncode == 2
    assert "github.official[1]" in result.stderr
    assert not paths["out"].exists()
    assert not paths["db"].exists()
