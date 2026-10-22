import json
import shutil
import sqlite3

import pytest

from conftest import FIXTURES, NOW


def collect(cli, paths, fixture="walking", config=None, out=None, fixtures_dir=None):
    root = fixtures_dir or FIXTURES / fixture
    return cli(
        "collect",
        "--config",
        config or root / "config.yaml",
        "--fixtures",
        root,
        "--now",
        NOW,
        "--out",
        out or paths["out"],
        "--state-db",
        paths["db"],
    )


def test_collect_builds_candidate_pool_from_pubmed_fixture(cli, paths):
    result = collect(cli, paths)

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))

    assert pool["generated_at"] == NOW
    assert pool["date"] == "2026-10-22"
    assert pool["lookback_days"] == {"pubmed": 2}
    assert pool["sources"]["pubmed"]["status"] == "ok"
    assert pool["sources"]["pubmed"]["count"] == 2
    assert {paper["pmid"] for paper in pool["papers"]} == {"39000001", "39000002"}

    aging = next(p for p in pool["papers"] if p["pmid"] == "39000001")
    assert aging["title"] == "Single-cell multi-omics reveals aging trajectories in human tissues"
    assert "multi-omics" in aging["abstract"]
    assert aging["doi"] == "10.1000/aging-omics.1"
    assert aging["group"] == "G1"
    assert {"aging", "multi-omics"} <= set(aging["tags"])
    assert aging["source"] == "pubmed"
    assert aging["venue"] == "Nature Aging"
    assert aging["date"] == "2026-10-20"
    assert aging["authors"] == ["Wei Zhang", "Na Li"]
    assert aging["abstract_missing"] is False
    assert aging["url"] == "https://pubmed.ncbi.nlm.nih.gov/39000001/"

    spatial = next(p for p in pool["papers"] if p["pmid"] == "39000002")
    assert spatial["group"] == "G2"
    assert "spatial transcriptomics" in spatial["tags"]


def test_paper_without_abstract_stays_in_pool_with_marker(cli, paths):
    result = collect(cli, paths, fixture="no-abstract")

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert len(pool["papers"]) == 1
    paper = pool["papers"][0]

    assert paper["pmid"] == "39000003"
    assert paper["abstract"] == ""
    assert paper["abstract_missing"] is True
    assert "无摘要" in paper["tags"]
    assert paper["group"] == "G1"
    assert paper["tags"][:2] == ["aging", "multi-omics"]


def test_collect_reads_europepmc_and_marks_preprints(cli, paths):
    result = collect(cli, paths, fixture="multisource")

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))

    assert pool["lookback_days"] == {"pubmed": 2, "europepmc": 2}
    assert pool["sources"]["pubmed"]["status"] == "ok"
    assert pool["sources"]["pubmed"]["count"] == 2
    assert pool["sources"]["europepmc"]["status"] == "ok"
    assert pool["sources"]["europepmc"]["count"] == 4

    preprint = next(
        paper
        for paper in pool["papers"]
        if paper["doi"] == "10.21203/rs.3.rs-11150671/v1"
    )
    assert preprint["is_preprint"] is True
    assert preprint["source"] == "europepmc"
    assert preprint["venue"] == "Research Square"
    assert preprint["date"] == "2026-10-21"
    assert "Background" in preprint["abstract"]
    assert "<h4>" not in preprint["abstract"]


def test_same_doi_across_sources_appears_once_with_pubmed_fields(cli, paths):
    result = collect(cli, paths, fixture="multisource")

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert pool["candidate_count"] == 4

    matching = [
        paper for paper in pool["papers"] if paper["doi"] == "10.1000/aging-omics.1"
    ]
    assert len(matching) == 1
    merged = matching[0]
    assert merged["id"] == "doi:10.1000/aging-omics.1"
    assert merged["source"] == "pubmed"
    assert merged["venue"] == "Nature Aging"
    assert "Europe PMC abstract" not in merged["abstract"]
    assert "multi-omics process" in merged["abstract"]

    spatial = [paper for paper in pool["papers"] if paper["pmid"] == "39000002"]
    assert len(spatial) == 1
    assert spatial[0]["id"] == "doi:10.1000/spatial-atlas.2"
    assert spatial[0]["source"] == "pubmed"
    assert spatial[0]["venue"] == "Cell Systems"
    assert "Europe PMC copy" not in spatial[0]["abstract"]


def test_pushed_item_is_excluded_from_the_next_candidate_pool(cli, paths):
    first = collect(cli, paths, fixture="multisource")
    assert first.returncode == 0, first.stderr
    first_pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert first_pool["candidate_count"] == 4

    connection = sqlite3.connect(paths["db"])
    try:
        connection.execute(
            "INSERT INTO pushes (item_id, digest_date, pushed_at) VALUES (?, ?, ?)",
            (
                "doi:10.1000/aging-omics.1",
                "2026-10-22",
                "2026-10-22T08:00:00+08:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    second_out = paths["tmp"] / "second.json"
    second = collect(cli, paths, fixture="multisource", out=second_out)

    assert second.returncode == 0, second.stderr
    pool = json.loads(second_out.read_text(encoding="utf-8"))
    ids = {paper["id"] for paper in pool["papers"]}
    assert "doi:10.1000/aging-omics.1" not in ids
    assert "doi:10.1000/spatial-atlas.2" in ids
    assert pool["candidate_count"] == 3


def test_rerun_records_papers_once_and_appends_a_run(cli, paths):
    first = collect(cli, paths)
    assert first.returncode == 0, first.stderr
    first_pool = json.loads(paths["out"].read_text(encoding="utf-8"))

    second = collect(cli, paths)
    assert second.returncode == 0, second.stderr
    second_pool = json.loads(paths["out"].read_text(encoding="utf-8"))

    assert [p["id"] for p in first_pool["papers"]] == [p["id"] for p in second_pool["papers"]]

    connection = sqlite3.connect(paths["db"])
    try:
        paper_count, distinct_ids = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT id) FROM papers"
        ).fetchone()
        runs = connection.execute(
            "SELECT status, candidate_count FROM runs ORDER BY id"
        ).fetchall()
    finally:
        connection.close()

    assert paper_count == 2
    assert distinct_ids == 2
    assert runs == [("ok", 2), ("ok", 2)]


@pytest.mark.parametrize(
    ("broken_source", "broken_file", "remaining_source", "candidate_count"),
    [
        ("europepmc", "europepmc/search.json", "pubmed", 2),
        ("pubmed", "pubmed/efetch.xml", "europepmc", 4),
    ],
)
def test_one_broken_source_still_produces_candidates(
    cli, paths, tmp_path, broken_source, broken_file, remaining_source, candidate_count
):
    fixtures = tmp_path / "broken-source"
    shutil.copytree(FIXTURES / "multisource", fixtures)
    (fixtures / broken_file).write_text(
        "<PubmedArticleSet><PubmedArticle>" if broken_source == "pubmed" else "{not json",
        encoding="utf-8",
    )

    result = collect(cli, paths, fixtures_dir=fixtures)

    assert result.returncode == 0, result.stderr
    assert broken_source in result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert pool["sources"][broken_source]["status"] == "failed"
    assert pool["sources"][broken_source]["count"] == 0
    assert pool["sources"][broken_source]["error"]
    assert pool["sources"][remaining_source]["status"] == "ok"
    assert pool["candidate_count"] == candidate_count
    assert {paper["source"] for paper in pool["papers"]} == {remaining_source}

    connection = sqlite3.connect(paths["db"])
    try:
        status = connection.execute(
            "SELECT status FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "ok"
