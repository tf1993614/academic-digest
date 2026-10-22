import json
import shutil

from conftest import FIXTURES, NOW, enable_sources


def collect(cli, paths, fixture="preprints", config=None, fixtures_dir=None):
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
        paths["out"],
        "--state-db",
        paths["db"],
    )


def test_arxiv_keeps_only_new_announcements_within_the_lookback(cli, paths):
    result = collect(cli, paths)

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    arxiv = {
        paper["arxiv_id"]: paper
        for paper in pool["papers"]
        if paper["source"] == "arxiv"
    }

    assert set(arxiv) == {"2610.11111", "2610.66666"}
    assert pool["sources"]["arxiv"] == {"status": "ok", "count": 2}

    paper = arxiv["2610.11111"]
    assert paper["id"] == "arxiv:2610.11111"
    assert paper["is_preprint"] is True
    assert "预印本" in paper["tags"]
    assert paper["venue"] == "arXiv"
    assert paper["authors"] == ["Wei Zhang", "Na Li"]
    assert paper["date"] == "2026-10-22"
    assert paper["url"] == "https://arxiv.org/abs/2610.11111v1"
    assert paper["oa_url"] == "https://arxiv.org/pdf/2610.11111"
    assert "senescence" in paper["abstract"]

    history = arxiv["2610.66666"]
    assert history["date"] == "2026-10-19"
    assert history["authors"] == ["History Author"]
    assert "backfill" in history["abstract"]
    assert history["is_preprint"] is True


def test_arxiv_drops_replace_cross_and_stale_items(cli, paths):
    result = collect(cli, paths)

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    titles = {paper["title"] for paper in pool["papers"]}

    assert "Spatial transcriptomics atlas of the aging brain, revised" not in titles
    assert "Spatial aging atlas, revised" not in titles
    assert "Cross-listed single-cell benchmark" not in titles
    assert "Aging multi-omics preprint from last week" not in titles


def test_researchsquare_rss_supplies_abstract_authors_and_doi(cli, paths):
    result = collect(cli, paths)

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    paper = next(
        paper
        for paper in pool["papers"]
        if paper["doi"] == "10.21203/rs.3.rs-9999999/v1"
    )

    assert paper["source"] == "researchsquare"
    assert paper["is_preprint"] is True
    assert "预印本" in paper["tags"]
    assert paper["venue"] == "Research Square"
    assert paper["authors"] == ["Ailing Chen", "Bo Sun"]
    assert paper["date"] == "2026-10-21"
    assert "Spatial transcriptomics and single-cell" in paper["abstract"]
    assert paper["url"] == "https://www.researchsquare.com/article/rs-9999999/latest"
    assert pool["sources"]["researchsquare"] == {"status": "ok", "count": 2}

    titles = {item["title"] for item in pool["papers"]}
    assert "Rethinking university admission" not in titles
    assert "An aging multi-omics study from last week" not in titles


def test_biorxiv_and_medrxiv_are_off_by_default(cli, paths):
    result = collect(cli, paths)

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))

    assert set(pool["sources"]) == {"arxiv", "researchsquare"}
    assert {paper["source"] for paper in pool["papers"]} <= {
        "arxiv",
        "researchsquare",
    }


def test_enabling_biorxiv_and_medrxiv_adds_locally_filtered_candidates(
    cli, paths, tmp_path
):
    fixtures = tmp_path / "preprints-enabled"
    shutil.copytree(FIXTURES / "preprints", fixtures)
    enable_sources(fixtures, "biorxiv", "medrxiv")

    result = collect(cli, paths, fixtures_dir=fixtures)

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert pool["sources"]["biorxiv"] == {"status": "ok", "count": 2}
    assert pool["sources"]["medrxiv"] == {"status": "ok", "count": 1}

    biorxiv = next(
        paper
        for paper in pool["papers"]
        if paper["doi"] == "10.1101/2026.10.20.777777"
    )
    assert biorxiv["source"] == "biorxiv"
    assert biorxiv["is_preprint"] is True
    assert "预印本" in biorxiv["tags"]
    assert biorxiv["venue"] == "bioRxiv"
    assert biorxiv["authors"] == ["Doe, Cara", "Roe, Dan"]
    assert biorxiv["date"] == "2026-10-20"
    assert biorxiv["url"] == (
        "https://www.biorxiv.org/content/10.1101/2026.10.20.777777v2"
    )

    medrxiv = next(
        paper
        for paper in pool["papers"]
        if paper["doi"] == "10.1101/2026.10.21.888888"
    )
    assert medrxiv["source"] == "medrxiv"
    assert medrxiv["venue"] == "medRxiv"

    titles = {paper["title"] for paper in pool["papers"]}
    assert "A revised phylogeny of ferns" not in titles


def test_same_doi_from_a_preprint_and_a_journal_appears_once(cli, paths):
    result = collect(cli, paths, fixture="preprint-dedupe")

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))

    dois = [paper["doi"] for paper in pool["papers"]]
    assert len(dois) == len(set(dois))
    assert pool["candidate_count"] == 3

    merged = next(
        paper
        for paper in pool["papers"]
        if paper["doi"] == "10.1101/2026.10.20.777777"
    )
    assert merged["source"] == "europepmc"
    assert merged["venue"] == "Nature Neuroscience"
    assert merged["is_preprint"] is False
    assert "预印本" not in merged["tags"]
    assert "Published version abstract" in merged["abstract"]
    assert "bioRxiv preprint abstract" not in merged["abstract"]


def test_same_doi_from_two_preprint_sources_appears_once_with_preprint_marker(
    cli, paths
):
    result = collect(cli, paths, fixture="preprint-dedupe")

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))

    merged = next(
        paper
        for paper in pool["papers"]
        if paper["doi"] == "10.21203/rs.3.rs-9999999/v1"
    )
    assert merged["is_preprint"] is True
    assert "预印本" in merged["tags"]
    assert merged["venue"] == "Research Square"
    assert "Europe PMC preprint abstract" in merged["abstract"]

    unique = next(
        paper
        for paper in pool["papers"]
        if paper["doi"] == "10.21203/rs.3.rs-5555555/v1"
    )
    assert unique["source"] == "researchsquare"
    assert unique["is_preprint"] is True


def test_arxiv_lookback_must_cover_a_weekend(cli, paths):
    result = collect(
        cli,
        paths,
        config=FIXTURES / "configs" / "arxiv-lookback.yaml",
        fixtures_dir=FIXTURES / "preprints",
    )

    assert result.returncode == 2
    assert "lookback.arxiv" in result.stderr
    assert "at least 4" in result.stderr
    assert not paths["out"].exists()
    assert not paths["db"].exists()


def test_arxiv_requires_configured_categories(cli, paths):
    result = collect(
        cli,
        paths,
        config=FIXTURES / "configs" / "arxiv-no-categories.yaml",
        fixtures_dir=FIXTURES / "preprints",
    )

    assert result.returncode == 2
    assert "arxiv.categories" in result.stderr
    assert not paths["out"].exists()
    assert not paths["db"].exists()


def test_preprint_without_abstract_keeps_both_markers(cli, paths):
    result = collect(cli, paths, fixture="preprint-no-abstract")

    assert result.returncode == 0, result.stderr
    pool = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert pool["candidate_count"] == 1

    paper = pool["papers"][0]
    assert paper["abstract"] == ""
    assert paper["abstract_missing"] is True
    assert paper["is_preprint"] is True
    assert paper["tags"] == ["aging", "预印本", "无摘要"]
