"""Journal whitelist: config, live query construction, ranking bonus, and doctor.

The fixture seam replays recorded responses, so it never observes the live
query string. The two ``build_query`` tests are the narrow exception: they pin
the PubMed ``[Journal]`` and Europe PMC ``JOURNAL:`` clauses directly, the same
way the transport tests pin what the fixture layer cannot reach.
"""

import json
import shutil
from datetime import datetime

import pytest
import yaml

from academic_digest.config import load_config
from academic_digest.sources.europepmc import build_query as europepmc_query
from academic_digest.sources.pubmed import build_query as pubmed_query
from conftest import FIXTURES, NOW, run_collect


def write_config(tmp_path, journal_filter, base="walking"):
    """Copy a fixture config and set (or omit) ``journal_filter``."""

    config = yaml.safe_load(
        (FIXTURES / base / "config.yaml").read_text(encoding="utf-8")
    )
    if journal_filter is not None:
        config["journal_filter"] = journal_filter
    path = tmp_path / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def read_pool(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _now():
    return datetime.fromisoformat(NOW)


def test_journal_filter_defaults_to_unrestricted(cli, paths):
    doctor = cli(
        "doctor",
        "--config",
        FIXTURES / "walking" / "config.yaml",
        "--fixtures",
        FIXTURES / "walking",
        "--now",
        NOW,
    )
    assert doctor.returncode == 0, doctor.stderr
    assert "journal filter: unrestricted" in doctor.stdout

    result = run_collect(cli, paths, "walking")
    assert result.returncode == 0, result.stderr
    papers = read_pool(paths["out"])["papers"]
    assert [paper["journal_match"] for paper in papers] == [False, False]
    assert [paper["score"] for paper in papers] == [7, 5]


@pytest.mark.parametrize(
    "journal_filter",
    [
        ["Nature Aging", "Cell Systems"],
        ["  Nature   Aging ", "nature aging", "Cell Systems"],
    ],
)
def test_doctor_lists_and_normalizes_configured_journals(
    cli, paths, tmp_path, journal_filter
):
    config = write_config(tmp_path, journal_filter)

    result = cli(
        "doctor",
        "--config",
        config,
        "--fixtures",
        FIXTURES / "walking",
        "--now",
        NOW,
        "--out",
        paths["out"],
        "--state-db",
        paths["db"],
    )

    assert result.returncode == 0, result.stderr
    assert "journal filter: 2 journals (Nature Aging, Cell Systems)" in result.stdout


@pytest.mark.parametrize(
    ("journal_filter", "field"),
    [
        ("Nature Aging", "journal_filter"),
        ([""], "journal_filter[0]"),
        ([123], "journal_filter[0]"),
        (['Nature "Aging"'], "journal_filter[0]"),
    ],
)
def test_journal_filter_validation_names_the_bad_field(
    cli, paths, tmp_path, journal_filter, field
):
    config = write_config(tmp_path, journal_filter)

    result = run_collect(cli, paths, "walking", config=config)

    assert result.returncode == 2
    assert field in result.stderr
    assert not paths["out"].exists()
    assert not paths["db"].exists()


def test_pubmed_query_adds_a_journal_clause_only_when_configured(tmp_path):
    unrestricted = load_config(write_config(tmp_path, None))
    assert pubmed_query(unrestricted) == (
        '"aging"[tiab] OR "ageing"[tiab] OR "senescence"[tiab] OR '
        '"multi-omics"[tiab] OR "multiomics"[tiab] OR "single-cell"[tiab] OR '
        '"scRNA-seq"[tiab] OR "spatial transcriptomics"[tiab] OR "MERFISH"[tiab]'
    )

    filtered = load_config(
        write_config(tmp_path / "filtered", ["Nature Aging", "Cell Systems"])
    )
    query = pubmed_query(filtered)

    assert query.startswith("(")
    assert query.endswith(
        'AND ("Nature Aging"[Journal] OR "Cell Systems"[Journal])'
    )


def test_europepmc_query_adds_a_journal_clause_only_when_configured(tmp_path):
    unrestricted = load_config(write_config(tmp_path, None, base="ranking-freshness"))
    assert "JOURNAL:" not in europepmc_query(unrestricted, _now())

    filtered = load_config(
        write_config(
            tmp_path / "filtered",
            ["Nature Aging", "Cell Systems"],
            base="ranking-freshness",
        )
    )
    query = europepmc_query(filtered, _now())

    assert query.endswith(
        'AND (JOURNAL:"Nature Aging" OR JOURNAL:"Cell Systems")'
    )


def test_whitelist_bonus_raises_a_paper_and_changes_the_order(cli, paths, tmp_path):
    fixtures = tmp_path / "ranking-freshness"
    shutil.copytree(FIXTURES / "ranking-freshness", fixtures)
    search_path = fixtures / "europepmc" / "search.json"
    payload = json.loads(search_path.read_text(encoding="utf-8"))
    future = next(
        record
        for record in payload["resultList"]["result"]
        if record["id"] == "80000003"
    )
    future["journalTitle"] = "Nature Aging"
    search_path.write_text(json.dumps(payload), encoding="utf-8")

    base = tmp_path / "base.json"
    baseline = run_collect(
        cli,
        paths,
        "ranking-freshness",
        config=write_config(tmp_path / "base", None, base="ranking-freshness"),
        fixtures_dir=fixtures,
        out=base,
    )
    assert baseline.returncode == 0, baseline.stderr
    assert read_pool(base)["papers"][0]["id"] == "pmid:80000001"

    filtered = tmp_path / "filtered"
    filtered_config = write_config(
        filtered, ["nature aging"], base="ranking-freshness"
    )
    result = run_collect(
        cli,
        paths,
        "ranking-freshness",
        config=filtered_config,
        fixtures_dir=fixtures,
    )

    assert result.returncode == 0, result.stderr
    papers = read_pool(paths["out"])["papers"]
    assert papers[0]["id"] == "pmid:80000003"
    assert papers[0]["journal_match"] is True
    assert papers[0]["score"] == 5
    # With the bonus both papers score 5; the newer date (80000003) wins.
    assert papers[1]["id"] == "pmid:80000001"
    assert papers[1]["journal_match"] is False
    assert papers[1]["score"] == 5
