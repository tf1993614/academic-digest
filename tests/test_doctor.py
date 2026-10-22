import shutil

from conftest import FIXTURES, NOW, enable_sources


def doctor(cli, fixtures="walking", config=None, fixtures_dir=None):
    root = fixtures_dir or FIXTURES / fixtures
    args = [
        "doctor",
        "--config",
        config or root / "config.yaml",
        "--now",
        NOW,
    ]
    if fixtures is not None:
        args += ["--fixtures", root]
    return cli(*args)


def test_doctor_reports_config_and_pubmed_fixture_checks(cli):
    result = doctor(cli)

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "config" in output
    assert "timezone: Asia/Shanghai" in output
    assert "topic G1" in output
    assert "source pubmed" in output
    assert "2 records" in output
    assert "all checks passed" in output


def test_doctor_rejects_empty_topics_with_field_name(cli):
    result = doctor(cli, config=FIXTURES / "configs" / "bad-topics.yaml")

    assert result.returncode != 0
    assert "topics" in result.stderr
    assert "non-empty" in result.stderr


def test_doctor_rejects_broken_yaml(cli):
    result = doctor(cli, config=FIXTURES / "configs" / "broken.yaml")

    assert result.returncode != 0
    assert "config" in result.stderr
    assert "YAML" in result.stderr


def test_doctor_reports_missing_source_fixture(cli, tmp_path):
    empty = tmp_path / "empty-fixtures"
    empty.mkdir()
    result = cli(
        "doctor",
        "--config",
        FIXTURES / "walking" / "config.yaml",
        "--fixtures",
        empty,
        "--now",
        NOW,
    )

    assert result.returncode != 0
    assert "pubmed" in result.stderr
    assert "missing fixture" in result.stderr


def test_collect_fails_before_writing_on_bad_config(cli, paths):
    result = cli(
        "collect",
        "--config",
        FIXTURES / "configs" / "bad-topics.yaml",
        "--fixtures",
        FIXTURES / "walking",
        "--now",
        NOW,
        "--out",
        paths["out"],
        "--state-db",
        paths["db"],
    )

    assert result.returncode != 0
    assert "topics" in result.stderr
    assert not paths["out"].exists()
    assert not paths["db"].exists()


def test_doctor_reports_malformed_pubmed_xml(cli, tmp_path):
    fixtures = tmp_path / "broken-fixtures"
    shutil.copytree(FIXTURES / "walking", fixtures)
    (fixtures / "pubmed" / "efetch.xml").write_text(
        "<PubmedArticleSet><PubmedArticle>", encoding="utf-8"
    )

    result = cli(
        "doctor",
        "--config",
        fixtures / "config.yaml",
        "--fixtures",
        fixtures,
        "--now",
        NOW,
    )

    assert result.returncode != 0
    assert "pubmed" in result.stderr
    assert "invalid PubMed XML" in result.stderr


def test_doctor_names_the_empty_terms_field(cli):
    result = doctor(cli, config=FIXTURES / "configs" / "empty-terms.yaml")

    assert result.returncode != 0
    assert "topics[0].terms" in result.stderr
    assert "non-empty" in result.stderr


def test_doctor_reports_config_and_europepmc_fixture_checks(cli):
    result = doctor(cli, fixtures="multisource")

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "source pubmed" in output
    assert "source europepmc" in output
    assert "4 records" in output
    assert "all checks passed" in output


def test_doctor_reports_malformed_europepmc_json(cli, tmp_path):
    fixtures = tmp_path / "broken-europepmc"
    shutil.copytree(FIXTURES / "multisource", fixtures)
    (fixtures / "europepmc" / "search.json").write_text("{not json", encoding="utf-8")

    result = doctor(cli, fixtures_dir=fixtures)

    assert result.returncode != 0
    assert "europepmc" in result.stderr
    assert "invalid Europe PMC JSON" in result.stderr


def test_doctor_requires_the_pubmed_source_key(cli):
    result = doctor(cli, config=FIXTURES / "configs" / "no-pubmed.yaml")

    assert result.returncode != 0
    assert "sources.pubmed" in result.stderr
    assert "required" in result.stderr


def test_doctor_reports_preprint_source_fixture_checks(cli):
    result = doctor(cli, fixtures="preprints")

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "source arxiv" in output
    assert "source researchsquare" in output
    assert "new item" in output
    assert "all checks passed" in output


def test_doctor_reports_malformed_arxiv_rss(cli, tmp_path):
    fixtures = tmp_path / "broken-arxiv"
    shutil.copytree(FIXTURES / "preprints", fixtures)
    (fixtures / "arxiv" / "rss" / "cs.LG.xml").write_text(
        "<rss><channel>", encoding="utf-8"
    )

    result = doctor(cli, fixtures="preprints", fixtures_dir=fixtures)

    assert result.returncode != 0
    assert "arxiv" in result.stderr
    assert "invalid arXiv RSS" in result.stderr


def test_doctor_checks_biorxiv_when_the_source_is_enabled(cli, tmp_path):
    fixtures = tmp_path / "preprints-doctor"
    shutil.copytree(FIXTURES / "preprints", fixtures)
    enable_sources(fixtures, "biorxiv")

    result = doctor(cli, fixtures="preprints", fixtures_dir=fixtures)

    assert result.returncode == 0, result.stderr
    assert "source biorxiv" in result.stdout
    assert "2 records" in result.stdout
