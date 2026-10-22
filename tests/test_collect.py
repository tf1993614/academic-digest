import json
import sqlite3

from conftest import FIXTURES, NOW


def collect(cli, paths, fixture="walking", config=None, out=None):
    return cli(
        "collect",
        "--config",
        config or FIXTURES / fixture / "config.yaml",
        "--fixtures",
        FIXTURES / fixture,
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
