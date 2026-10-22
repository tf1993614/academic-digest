import shutil

from conftest import FIXTURES, NOW


def doctor(cli, fixtures="walking", config=None):
    args = ["doctor", "--config", config or FIXTURES / fixtures / "config.yaml"]
    if fixtures is not None:
        args += ["--fixtures", FIXTURES / fixtures]
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
    )

    assert result.returncode != 0
    assert "pubmed" in result.stderr
    assert "invalid PubMed XML" in result.stderr


def test_doctor_names_the_empty_terms_field(cli):
    result = doctor(cli, config=FIXTURES / "configs" / "empty-terms.yaml")

    assert result.returncode != 0
    assert "topics[0].terms" in result.stderr
    assert "non-empty" in result.stderr
