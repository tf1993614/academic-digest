import json
from collections import Counter

import yaml

from conftest import FIXTURES, run_collect

MARKER_TAGS = {"预印本", "无摘要"}


def read_pool(paths):
    return json.loads(paths["out"].read_text(encoding="utf-8"))


def test_broad_group_is_capped_and_a_narrow_group_keeps_its_best(cli, paths):
    result = run_collect(cli, paths, "ranking-quota")

    assert result.returncode == 0, result.stderr
    pool = read_pool(paths)
    papers = pool["papers"]

    assert pool["candidate_count"] == 6
    assert len(papers) == 6
    assert Counter(paper["group"] for paper in papers) == {"G2": 4, "G3": 1, "G1": 1}

    # G1's best paper survives even though every G2/G3 paper outranks it.
    assert {paper["id"] for paper in papers if paper["group"] == "G1"} == {"pmid:70000001"}

    # Score is relevance plus freshness: a title hit is 3, today adds 2.
    by_id = {paper["id"]: paper for paper in papers}
    assert by_id["pmid:50000001"]["score"] == 5
    assert by_id["pmid:70000001"]["score"] == 3

    # Equal scores and dates fall back to the id, so the order is reproducible.
    assert [paper["id"] for paper in papers] == [
        "pmid:50000001",
        "pmid:50000002",
        "pmid:50000003",
        "pmid:50000004",
        "pmid:60000001",
        "pmid:70000001",
    ]


def test_candidate_pool_is_capped_at_thirty_by_default(cli, paths):
    result = run_collect(cli, paths, "ranking-cap")

    assert result.returncode == 0, result.stderr
    pool = read_pool(paths)
    papers = pool["papers"]

    assert pool["candidate_count"] == 30
    assert len(papers) == 30
    assert len({paper["id"] for paper in papers}) == 30

    # 34 candidates compete: G1 loses its 11th, G2 stops at four, and the two
    # lowest-ranked G5 papers miss the last slots.
    counts = Counter(paper["group"] for paper in papers)
    assert counts == {"G1": 10, "G2": 4, "G3": 6, "G4": 6, "G5": 4}
    assert papers[0]["id"] == "doi:10.1000/cap-g1-01"


def test_every_candidate_explains_its_hit_with_its_group_terms(cli, paths, tmp_path):
    for fixture in ("ranking-quota", "ranking-cap"):
        out = tmp_path / f"{fixture}.json"
        result = run_collect(cli, paths, fixture, out=out)

        assert result.returncode == 0, result.stderr
        config = yaml.safe_load((FIXTURES / fixture / "config.yaml").read_text(encoding="utf-8"))
        terms = {topic["name"]: set(topic["terms"]) for topic in config["topics"]}
        papers = json.loads(out.read_text(encoding="utf-8"))["papers"]

        for paper in papers:
            assert paper["group"] in terms
            hits = [tag for tag in paper["tags"] if tag not in MARKER_TAGS]
            assert hits, paper["id"]
            assert set(hits) <= terms[paper["group"]], paper["id"]
            text = f'{paper["title"]} {paper["abstract"]}'.lower()
            assert all(tag.lower() in text for tag in hits), paper["id"]


def test_short_candidate_list_is_not_padded(cli, paths):
    result = run_collect(cli, paths, "walking")

    assert result.returncode == 0, result.stderr
    pool = read_pool(paths)
    papers = pool["papers"]

    assert pool["candidate_count"] == 2
    assert len(papers) == 2
    assert all(paper["id"] and paper["title"] and paper["group"] for paper in papers)
    assert all(paper["tags"] for paper in papers)


def test_freshness_bonus_and_date_tie_break_are_fixed_for_a_given_clock(cli, paths):
    result = run_collect(cli, paths, "ranking-freshness")

    assert result.returncode == 0, result.stderr
    papers = read_pool(paths)["papers"]

    # A title hit is 3 and an abstract hit is 1. Today adds 2, yesterday 1, and
    # future/older dates add nothing.
    assert [(paper["id"], paper["relevance"], paper["score"]) for paper in papers] == [
        ("pmid:80000001", 3, 5),
        ("pmid:80000002", 3, 4),
        ("pmid:80000003", 3, 3),
        ("pmid:80000004", 3, 3),
        ("pmid:80000005", 3, 3),
        ("pmid:80000006", 1, 1),
    ]

    # The score-3 papers tie, so the newer publication date wins; a year-only
    # date has no day precision and sorts after every dated paper.
    assert [paper["date"] for paper in papers[2:]] == [
        "2026-10-23",
        "2026-10-15",
        "2026",
        "2026-10-15",
    ]


def test_pool_cap_must_leave_room_for_every_group(cli, paths):
    result = run_collect(
        cli,
        paths,
        "walking",
        config=FIXTURES / "configs" / "pool-too-small.yaml",
    )

    assert result.returncode == 2
    assert "pool.max_items" in result.stderr
    assert "at least the number of topics (2)" in result.stderr
    assert not paths["out"].exists()
    assert not paths["db"].exists()


def test_freshness_uses_the_configured_timezone(cli, paths):
    # 18:00 UTC on the 21st is already the 22nd in Asia/Shanghai, so the
    # 22nd-dated paper counts as today rather than as a future date.
    result = run_collect(
        cli, paths, "ranking-freshness", now="2026-10-21T18:00:00+00:00"
    )

    assert result.returncode == 0, result.stderr
    scores = {paper["id"]: paper["score"] for paper in read_pool(paths)["papers"]}
    assert scores["pmid:80000001"] == 5
    assert scores["pmid:80000002"] == 4


def test_topic_default_quota_is_six(cli, paths):
    result = run_collect(cli, paths, "ranking-default-quota")

    assert result.returncode == 0, result.stderr
    papers = read_pool(paths)["papers"]

    assert len(papers) == 6
    assert [paper["id"] for paper in papers] == [
        f"pmid:9000000{n}" for n in range(1, 7)
    ]
