import json
import shutil

from conftest import FIXTURES, run_fulltext

CONFIG = FIXTURES / "fulltext" / "config.yaml"


def _result(paths):
    return json.loads(paths["out"].read_text(encoding="utf-8"))


def _extracted_length(data):
    paragraphs = [*data["methods"], *data["results"], *data["limitations"]]
    return sum(len(paragraph) for paragraph in paragraphs)


def test_europepmc_oa_xml_extracts_methods_results_and_limitations(cli, paths):
    result = run_fulltext(cli, paths, "epmc", "--doi", "10.1000/oa-epmc.1")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["oa"] is True
    assert data["source"] == "europepmc"
    assert data["format"] == "xml"
    assert data["doi"] == "10.1000/oa-epmc.1"
    assert data["url"] == "https://europepmc.org/articles/PMC1234567"
    assert data["methods"][0].startswith("We performed single-cell RNA sequencing")
    assert any("10x Genomics" in paragraph for paragraph in data["methods"])
    assert data["results"][0].startswith("Aged brains showed")
    assert data["limitations"][0].startswith("Our study has limitations")
    assert "These results suggest" not in " ".join(data["limitations"])
    assert data["length"] == _extracted_length(data)
    assert data["length"] > 0
    assert data["attempts"] == [
        {
            "source": "europepmc",
            "status": "ok",
            "url": "https://europepmc.org/articles/PMC1234567",
        }
    ]


def test_arxiv_html_extracts_sections_including_nested_methods(cli, paths):
    result = run_fulltext(cli, paths, "arxiv-html", "--arxiv", "2610.11111v2")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "arxiv"
    assert data["format"] == "html"
    assert data["arxiv_id"] == "2610.11111"
    assert data["url"] == "https://arxiv.org/html/2610.11111"
    assert len(data["methods"]) == 3
    assert data["methods"][0].startswith("We trained a graph neural network")
    assert data["methods"][1].startswith("The encoder uses")
    assert any("five-fold cross-validation" in paragraph for paragraph in data["methods"])
    assert data["results"][0].startswith("The model achieved an AUROC")
    assert data["limitations"][0].startswith("A limitation of this work")
    assert "Abstract" not in " ".join(data["methods"])
    assert "We study representation transfer" not in " ".join(data["methods"])
    assert data["length"] == _extracted_length(data)


def test_arxiv_pdf_is_used_when_the_html_record_is_missing(cli, paths):
    result = run_fulltext(cli, paths, "arxiv-pdf", "--arxiv", "2610.22222")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "arxiv"
    assert data["format"] == "pdf"
    assert data["url"] == "https://arxiv.org/pdf/2610.22222"
    assert data["methods"][0].startswith("We trained a graph neural network")
    assert any("five-fold cross-validation" in paragraph for paragraph in data["methods"])
    assert data["results"][0].startswith("The model achieved an AUROC")
    assert data["limitations"][0].startswith("A limitation of this work")
    assert data["length"] == _extracted_length(data)
    # The HTML miss and PDF success are one source attempt, not two.
    assert data["attempts"] == [
        {
            "source": "arxiv",
            "status": "ok",
            "url": "https://arxiv.org/pdf/2610.22222",
        }
    ]


def test_biorxiv_doi_extracts_from_the_preprint_pdf(cli, paths):
    result = run_fulltext(cli, paths, "biorxiv", "--doi", "10.1101/2026.10.20.777777")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "biorxiv"
    assert data["format"] == "pdf"
    assert data["doi"] == "10.1101/2026.10.20.777777"
    assert data["url"] == (
        "https://www.biorxiv.org/content/10.1101/2026.10.20.777777.full.pdf"
    )
    assert data["methods"][0].startswith("We collected 12,000 cells")
    assert any("Illumina NovaSeq" in paragraph for paragraph in data["methods"])
    assert data["results"][0].startswith("Aged brains showed")
    assert data["limitations"][0].startswith("Our study has several limitations")
    assert data["length"] == _extracted_length(data)


def test_researchsquare_doi_extracts_from_the_preprint_pdf(cli, paths):
    result = run_fulltext(
        cli, paths, "researchsquare", "--doi", "10.21203/rs.3.rs-9999999/v1"
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "researchsquare"
    assert data["format"] == "pdf"
    assert data["doi"] == "10.21203/rs.3.rs-9999999/v1"
    assert data["url"] == (
        "https://www.researchsquare.com/article/rs-9999999/latest.pdf"
    )
    assert data["methods"][0].startswith("We applied a CRISPR screen")
    assert data["results"][0].startswith("The screen recovered")
    assert data["limitations"][0].startswith("A key limitation")
    assert data["length"] == _extracted_length(data)


def test_unpaywall_locates_an_oa_pdf(cli, paths):
    result = run_fulltext(cli, paths, "unpaywall", "--doi", "10.1000/unpaywall-oa.1")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "unpaywall"
    assert data["format"] == "pdf"
    assert data["url"] == "https://repository.example.org/article.pdf"
    assert data["methods"][0].startswith("We fitted a mixed-effects model")
    assert data["results"][0].startswith("The model explained")
    assert data["limitations"][0].startswith("The observational design")
    assert data["length"] == _extracted_length(data)


def test_no_oa_is_a_status_not_an_error(cli, paths):
    result = run_fulltext(cli, paths, "no-oa", "--doi", "10.9999/closed.1")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "no_oa"
    assert data["oa"] is False
    assert data["source"] == ""
    assert data["format"] == ""
    assert data["url"] == ""
    assert data["methods"] == []
    assert data["results"] == []
    assert data["limitations"] == []
    assert data["length"] == 0
    assert "no open-access" in data["reason"]
    assert "test@example.com" not in json.dumps(data)
    assert any(
        attempt["source"] == "unpaywall" and attempt["status"] == "miss"
        for attempt in data["attempts"]
    )


def test_missing_fixtures_degrade_to_no_oa(cli, paths, tmp_path):
    empty = tmp_path / "empty-fixtures"
    empty.mkdir()

    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        empty,
        "--doi",
        "10.9999/missing.1",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)
    assert data["status"] == "no_oa"
    assert data["reason"].startswith("no open-access full text")
    assert [attempt["source"] for attempt in data["attempts"]] == [
        "europepmc",
        "unpaywall",
    ]


def test_fulltext_requires_a_target(cli, paths):
    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        FIXTURES / "fulltext" / "epmc",
        "--out",
        paths["out"],
    )

    assert result.returncode == 2
    assert "--doi, --arxiv or --title" in result.stderr


def test_invalid_unpaywall_email_fails_before_any_fetch(cli, paths):
    result = cli(
        "fulltext",
        "--config",
        FIXTURES / "configs" / "bad-unpaywall-email.yaml",
        "--fixtures",
        FIXTURES / "fulltext" / "epmc",
        "--doi",
        "10.1000/oa-epmc.1",
        "--out",
        paths["out"],
    )

    assert result.returncode == 2
    assert "fulltext.unpaywall.email" in result.stderr


def test_medrxiv_doi_extracts_from_the_server_pdf(cli, paths):
    result = run_fulltext(cli, paths, "medrxiv", "--doi", "10.1101/2026.10.21.888888")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "medrxiv"
    assert data["format"] == "pdf"
    assert data["url"] == (
        "https://www.medrxiv.org/content/10.1101/2026.10.21.888888.full.pdf"
    )
    assert data["methods"][0].startswith("We treated 6,000 cells")
    assert data["results"][0].startswith("Drug treatment shifted")
    assert data["limitations"][0].startswith("Only one cell line")
    assert data["length"] == _extracted_length(data)


def test_unpaywall_html_location_is_extracted_as_html(cli, paths):
    result = run_fulltext(
        cli, paths, "unpaywall-html", "--doi", "10.1000/unpaywall-html.1"
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "unpaywall"
    assert data["format"] == "html"
    assert data["url"] == "https://repository.example.org/html-article"
    assert data["methods"][0].startswith("We analyzed 3,200 samples")
    assert data["results"][0].startswith("The model identified")
    assert data["limitations"][0].startswith("A limitation of this analysis")
    assert data["length"] == _extracted_length(data)


def test_section_paragraph_caps(cli, paths):
    result = run_fulltext(cli, paths, "truncation", "--doi", "10.1000/truncation.1")

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert len(data["methods"]) == 4
    assert len(data["results"]) == 3
    assert len(data["limitations"]) == 4
    assert data["length"] == _extracted_length(data)


def test_europepmc_is_tried_before_unpaywall(cli, paths, tmp_path):
    root = tmp_path / "order"
    shutil.copytree(FIXTURES / "fulltext" / "epmc" / "europepmc", root / "europepmc")
    shutil.copytree(
        FIXTURES / "fulltext" / "unpaywall" / "unpaywall", root / "unpaywall"
    )

    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        root,
        "--doi",
        "10.1000/oa-epmc.1",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)
    assert data["source"] == "europepmc"
    assert [attempt["source"] for attempt in data["attempts"]] == ["europepmc"]


def test_arxiv_is_tried_before_the_preprint_pdf(cli, paths, tmp_path):
    root = tmp_path / "order-arxiv"
    shutil.copytree(FIXTURES / "fulltext" / "arxiv-html" / "arxiv", root / "arxiv")
    shutil.copytree(
        FIXTURES / "fulltext" / "biorxiv" / "biorxiv", root / "biorxiv"
    )
    shutil.copytree(
        FIXTURES / "fulltext" / "unpaywall" / "unpaywall", root / "unpaywall"
    )

    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        root,
        "--doi",
        "10.1101/2026.10.20.777777",
        "--arxiv",
        "2610.33333",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)
    assert data["source"] == "arxiv"
    assert data["format"] == "html"
    assert data["url"] == "https://arxiv.org/html/2610.33333"
    assert [attempt["source"] for attempt in data["attempts"]] == [
        "europepmc",
        "arxiv",
    ]


def test_missing_unpaywall_email_skips_the_attempt(cli, paths, tmp_path):
    empty = tmp_path / "empty-fixtures"
    empty.mkdir()

    result = cli(
        "fulltext",
        "--config",
        FIXTURES / "fulltext" / "config-no-email.yaml",
        "--fixtures",
        empty,
        "--doi",
        "10.9999/missing.1",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)
    assert data["status"] == "no_oa"
    assert [attempt["source"] for attempt in data["attempts"]] == ["europepmc"]
    assert "unpaywall" not in data["reason"]


def test_fulltext_prints_json_to_stdout_without_out(cli):
    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        FIXTURES / "fulltext" / "epmc",
        "--doi",
        "10.1000/oa-epmc.1",
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "oa"
    assert data["source"] == "europepmc"
    assert "[oa]" in result.stderr


def test_character_caps_truncate_at_sentence_boundaries(cli, paths):
    result = run_fulltext(
        cli, paths, "truncation-chars", "--doi", "10.1000/truncation-chars.1"
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert len(data["methods"]) == 1
    assert sum(len(paragraph) for paragraph in data["methods"]) <= 4000
    assert data["methods"][0].endswith(".")

    assert len(data["results"]) == 1
    assert sum(len(paragraph) for paragraph in data["results"]) <= 3000
    assert data["results"][0].endswith(".")

    assert len(data["limitations"]) == 1
    assert sum(len(paragraph) for paragraph in data["limitations"]) <= 2000
    assert data["limitations"][0].endswith(".")
    assert data["length"] == _extracted_length(data)


def test_unpaywall_is_reached_after_preprint_misses(cli, paths, tmp_path):
    root = tmp_path / "order-unpaywall"
    shutil.copytree(
        FIXTURES / "fulltext" / "unpaywall" / "unpaywall", root / "unpaywall"
    )

    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        root,
        "--doi",
        "10.1101/2026.10.20.777777",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)
    assert data["source"] == "unpaywall"
    assert [attempt["source"] for attempt in data["attempts"]] == [
        "europepmc",
        "biorxiv",
        "medrxiv",
        "unpaywall",
    ]
    assert all(
        attempt["status"] == "miss" for attempt in data["attempts"][:3]
    )


def test_arxiv_miss_falls_through_to_the_preprint_pdf(cli, paths, tmp_path):
    root = tmp_path / "arxiv-miss"
    shutil.copytree(
        FIXTURES / "fulltext" / "biorxiv" / "biorxiv", root / "biorxiv"
    )

    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        root,
        "--doi",
        "10.1101/2026.10.20.777777",
        "--arxiv",
        "2610.44444",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)
    assert data["source"] == "biorxiv"
    assert [attempt["source"] for attempt in data["attempts"]] == [
        "europepmc",
        "arxiv",
        "biorxiv",
    ]
    assert [attempt["status"] for attempt in data["attempts"]] == [
        "miss",
        "miss",
        "ok",
    ]


def test_title_matches_a_preprint_version_with_a_different_doi(cli, paths):
    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        FIXTURES / "fulltext" / "title-match",
        "--title",
        "Aging brains at single-cell resolution",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "biorxiv"
    assert data["doi"] == "10.1101/2026.10.20.777777"
    assert data["url"] == (
        "https://www.biorxiv.org/content/10.1101/2026.10.20.777777.full.pdf"
    )
    assert [attempt["source"] for attempt in data["attempts"]] == ["biorxiv"]


def test_title_matching_requires_an_exact_title(cli, paths):
    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        FIXTURES / "fulltext" / "title-mismatch",
        "--title",
        "Aging brains at single-cell resolution",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "no_oa"
    assert data["attempts"] == []


def test_a_doi_finds_its_arxiv_version_through_the_title(cli, paths):
    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        FIXTURES / "fulltext" / "arxiv-title",
        "--doi",
        "10.1000/journal.1",
        "--title",
        "Single-cell foundation models for perturbation prediction",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "arxiv"
    assert data["arxiv_id"] == "2610.44444"
    assert data["url"] == "https://arxiv.org/html/2610.44444"
    assert [attempt["source"] for attempt in data["attempts"]] == [
        "europepmc",
        "arxiv",
    ]


def test_an_arxiv_doi_maps_directly_to_the_arxiv_id(cli, paths):
    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        FIXTURES / "fulltext" / "arxiv-title",
        "--doi",
        "10.48550/arXiv.2610.44444",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "oa"
    assert data["source"] == "arxiv"
    assert data["arxiv_id"] == "2610.44444"


def test_a_title_only_lookup_returns_no_oa_when_nothing_matches(cli, paths, tmp_path):
    empty = tmp_path / "empty-fixtures"
    empty.mkdir()

    result = cli(
        "fulltext",
        "--config",
        CONFIG,
        "--fixtures",
        empty,
        "--title",
        "Nothing matches this title",
        "--out",
        paths["out"],
    )

    assert result.returncode == 0, result.stderr
    data = _result(paths)

    assert data["status"] == "no_oa"
    assert data["attempts"] == []
