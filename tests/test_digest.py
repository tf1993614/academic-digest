import json
import shutil

from conftest import FIXTURES, run_digest

VALID = FIXTURES / "digest" / "valid"
EMPTY = FIXTURES / "digest" / "empty"


def _case(tmp_path):
    case = tmp_path / "case"
    shutil.copytree(VALID, case)
    return case


def _load(case, name):
    return json.loads((case / name).read_text(encoding="utf-8"))


def _save(case, name, payload):
    (case / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _digest(case):
    return (case / "digest.md").read_text(encoding="utf-8")


def _write_digest(case, text):
    (case / "digest.md").write_text(text, encoding="utf-8")


def _replace_selection_paper(selection, index, paper):
    selection["papers"][index] = paper


def _remove_quick_line(text, title):
    return "\n".join(
        line for line in text.split("\n") if not line.startswith(f"- **{title}**")
    )


def test_a_complete_digest_passes(cli):
    result = run_digest(cli, VALID)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert (
        "[ok] digest: 10 papers (3 must_read + 7 quick_scan), 8 GitHub items"
        in result.stdout
    )


def test_empty_candidate_pool_allows_a_title_and_footer_only_digest(cli):
    result = run_digest(cli, EMPTY)

    assert result.returncode == 0, result.stderr
    assert "0 papers (0 must_read + 0 quick_scan), 0 GitHub items" in result.stdout


def test_unknown_selection_id_fails(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    selection["papers"][0]["id"] = "doi:10.1000/missing"
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection:" in result.stderr
    assert "is not in candidates.papers" in result.stderr


def test_selection_date_must_match_the_candidate_pool(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    selection["date"] = "2026-10-21"
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: date 2026-10-21" in result.stderr


def test_g2_is_capped_at_four_papers(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    _replace_selection_paper(
        selection,
        8,
        {
            "id": "doi:10.1000/digest-g2-5",
            "group": "G2",
            "section": "quick_scan",
            "reason": "第五篇 G2",
            "fulltext": "abstract_only",
            "limitations_source": ["author"],
        },
    )
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: G2 has 5 papers" in result.stderr


def test_every_non_empty_group_needs_a_paper(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    _replace_selection_paper(
        selection,
        8,
        {
            "id": "doi:10.1000/digest-g5-2",
            "group": "G5",
            "section": "quick_scan",
            "reason": "补位",
            "fulltext": "abstract_only",
            "limitations_source": ["author"],
        },
    )
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: group G4 has no paper" in result.stderr


def test_must_read_needs_a_model_limitation(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    selection["papers"][0]["limitations_source"] = ["author"]
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection:" in result.stderr
    assert "must include 'model'" in result.stderr


def test_quick_scan_can_only_claim_abstract_only(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    selection["papers"][3]["fulltext"] = "oa"
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection:" in result.stderr
    assert "must be 'abstract_only' for quick_scan" in result.stderr


def test_must_read_count_must_meet_the_target(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    selection["papers"][0]["section"] = "quick_scan"
    selection["papers"][0]["fulltext"] = "abstract_only"
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: must_read has 2 papers, expected 3" in result.stderr


def test_quick_scan_shortfall_is_allowed_only_when_the_g2_quota_blocks_it(
    cli, tmp_path
):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates["papers"] = [
        paper
        for paper in candidates["papers"]
        if paper["id"] not in {"doi:10.1000/digest-g4-1", "doi:10.1000/digest-g5-2"}
    ]
    candidates["candidate_count"] = len(candidates["papers"])
    _save(case, "candidates.json", candidates)

    selection = _load(case, "selection.json")
    selection["papers"] = [
        paper for paper in selection["papers"] if paper["id"] != "doi:10.1000/digest-g4-1"
    ]
    _save(case, "selection.json", selection)

    digest = _remove_quick_line(
        _digest(case), "Perturbation prediction with graph priors"
    )
    digest = digest.replace("候选：12", "候选：10").replace("入选：10", "入选：9")
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 0, result.stderr


def test_quick_scan_shortfall_is_rejected_when_another_candidate_could_fill_it(
    cli, tmp_path
):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    selection["papers"] = [
        paper for paper in selection["papers"] if paper["id"] != "doi:10.1000/digest-g4-1"
    ]
    _save(case, "selection.json", selection)

    digest = _remove_quick_line(
        _digest(case), "Perturbation prediction with graph priors"
    )
    digest = digest.replace("入选：10", "入选：9")
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: quick_scan has 6 papers, expected 7" in result.stderr


def test_a_g6_paper_can_only_appear_in_quick_scan(cli, tmp_path):
    case = _case(tmp_path)
    selection = _load(case, "selection.json")
    selection["papers"][2]["section"] = "quick_scan"
    selection["papers"][2]["fulltext"] = "abstract_only"
    selection["papers"][9]["section"] = "must_read"
    selection["papers"][9]["fulltext"] = "abstract_only"
    selection["papers"][9]["limitations_source"] = ["author", "model"]
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: G6 paper" in result.stderr
    assert "must be in quick_scan" in result.stderr


def test_abstract_only_must_read_must_say_so_in_the_digest(cli, tmp_path):
    case = _case(tmp_path)
    digest = _digest(case).replace(
        "- 方法精读：无 OA 全文，仅基于摘要",
        "- 方法精读：基于摘要的方法概述",
    )
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest:" in result.stderr
    assert "abstract_only" in result.stderr


def test_an_oa_must_read_may_not_claim_it_only_has_the_abstract(cli, tmp_path):
    case = _case(tmp_path)
    digest = _digest(case).replace(
        "- 方法精读：作者先用单细胞多组学建库，再按年龄分层做差异分析，"
        "并用独立队列验证关键细胞类型。方法部分交代了批次校正与质控阈值。",
        "- 方法精读：无 OA 全文，仅基于摘要",
    )
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest:" in result.stderr
    assert "is oa but" in result.stderr


def test_digest_title_date_must_match_the_candidate_pool(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(
        case,
        _digest(case).replace("# 学术速递 · 2026-10-22", "# 学术速递 · 2026-10-21"),
    )

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: title date 2026-10-21" in result.stderr


def test_a_translated_title_is_rejected(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(
        case,
        _digest(case).replace(
            "**Plasma proteomics of aging cohorts**",
            "**衰老队列的血浆蛋白组**",
        ),
    )

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: 其它速览" in result.stderr
    assert "missing the paper" in result.stderr


def test_a_repeated_title_is_rejected(cli, tmp_path):
    case = _case(tmp_path)
    digest = _digest(case)
    line = next(
        line
        for line in digest.split("\n")
        if line.startswith("- **Plasma proteomics of aging cohorts**")
    )
    _write_digest(case, digest.replace(line, f"{line}\n{line}"))

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: 其它速览 repeats the paper title" in result.stderr


def test_a_missing_github_item_is_rejected(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(
        case,
        "\n".join(
            line
            for line in _digest(case).split("\n")
            if not line.startswith("- **acme/cell-atlas**")
        ),
    )

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: 新项目 is missing acme/cell-atlas" in result.stderr


def test_an_extra_github_item_is_rejected(cli, tmp_path):
    case = _case(tmp_path)
    digest = _digest(case).replace(
        "### 活跃项目",
        "- **acme/unknown** ⭐ 1 · Go · 2026-10-21 · Unknown · Why · "
        "[链接](https://github.com/acme/unknown)\n### 活跃项目",
    )
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: 新项目 has an unexpected item" in result.stderr


def test_github_sections_must_be_omitted_when_the_pool_has_no_items(cli, tmp_path):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates.pop("github")
    _save(case, "candidates.json", candidates)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "'## GitHub' must be omitted" in result.stderr


def test_a_digest_without_github_sections_passes_when_the_pool_has_no_items(
    cli, tmp_path
):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates.pop("github")
    _save(case, "candidates.json", candidates)

    digest = _digest(case)
    head, _, rest = digest.partition("\n## GitHub")
    footer = rest[rest.index("\n---\n") :]
    _write_digest(case, head + footer)

    result = run_digest(cli, case)

    assert result.returncode == 0, result.stderr


def test_g6_item_count_must_stay_within_the_candidate_limit(cli, tmp_path):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates["github"]["g6"].append(
        {**candidates["github"]["g6"][0], "full_name": "acme/third-tool"}
    )
    _save(case, "candidates.json", candidates)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] candidates: github.g6 has 3 items" in result.stderr


def test_footer_candidate_count_must_match_the_pool(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(case, _digest(case).replace("候选：12", "候选：30"))

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: footer 候选：30" in result.stderr


def test_footer_must_report_every_source_status(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(case, _digest(case).replace(" ｜ github ok (5)", ""))

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: footer 来源： does not report github ok" in result.stderr


def test_footer_must_not_contain_a_secret(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(case, _digest(case).replace("来源：", "来源：sctp12345 ", 1))

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: contains a secret-like token" in result.stderr


def test_missing_digest_argument_is_a_usage_error(cli):
    result = cli(
        "digest",
        "check",
        "--candidates",
        VALID / "candidates.json",
        "--selection",
        VALID / "selection.json",
    )

    assert result.returncode == 2
    assert "--digest" in result.stderr


def test_an_unreadable_file_fails_with_exit_one(cli, tmp_path):
    case = _case(tmp_path)
    (case / "digest.md").unlink()

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: cannot read" in result.stderr


def test_invalid_selection_json_fails_with_exit_one(cli, tmp_path):
    case = _case(tmp_path)
    (case / "selection.json").write_text("{", encoding="utf-8")

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: invalid JSON" in result.stderr


def test_a_short_pool_can_omit_must_reads_that_g6_cannot_fill(cli):
    result = run_digest(cli, FIXTURES / "digest" / "g6-short-pool")

    assert result.returncode == 0, result.stderr
    assert "2 papers (1 must_read + 1 quick_scan)" in result.stdout


def test_a_must_read_shortfall_is_rejected_when_a_non_g6_candidate_remains(
    cli, tmp_path
):
    case = tmp_path / "case"
    shutil.copytree(FIXTURES / "digest" / "g6-short-pool", case)
    candidates = _load(case, "candidates.json")
    candidates["papers"].append(
        {
            "id": "doi:10.1000/digest-g2-1",
            "group": "G2",
            "title": "Spatial transcriptomics of the aging cortex",
        }
    )
    candidates["candidate_count"] = len(candidates["papers"])
    _save(case, "candidates.json", candidates)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: must_read has 1 papers, expected 3" in result.stderr


def test_a_second_g6_paper_is_rejected(cli, tmp_path):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates["papers"].append(
        {
            "id": "doi:10.1000/digest-g6-2",
            "group": "G6",
            "title": "Second G6 paper",
        }
    )
    candidates["candidate_count"] = len(candidates["papers"])
    _save(case, "candidates.json", candidates)

    selection = _load(case, "selection.json")
    _replace_selection_paper(
        selection,
        5,
        {
            "id": "doi:10.1000/digest-g6-2",
            "group": "G6",
            "section": "quick_scan",
            "reason": "第二个 G6",
            "fulltext": "abstract_only",
            "limitations_source": ["author"],
        },
    )
    _save(case, "selection.json", selection)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] selection: G6 has 2 papers, the maximum is 1" in result.stderr


def test_a_quick_scan_shortfall_is_allowed_when_the_g6_cap_blocks_it(cli, tmp_path):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates["papers"] = [
        paper
        for paper in candidates["papers"]
        if paper["id"] not in {"doi:10.1000/digest-g4-1", "doi:10.1000/digest-g5-2"}
    ]
    candidates["papers"].append(
        {
            "id": "doi:10.1000/digest-g6-2",
            "group": "G6",
            "title": "Second G6 paper",
        }
    )
    candidates["candidate_count"] = len(candidates["papers"])
    _save(case, "candidates.json", candidates)

    selection = _load(case, "selection.json")
    selection["papers"] = [
        paper for paper in selection["papers"] if paper["id"] != "doi:10.1000/digest-g4-1"
    ]
    _save(case, "selection.json", selection)

    digest = _remove_quick_line(
        _digest(case), "Perturbation prediction with graph priors"
    )
    digest = digest.replace("候选：12", "候选：11").replace("入选：10", "入选：9")
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 0, result.stderr


def test_the_g6_item_limit_defaults_to_two_when_limits_are_absent(cli, tmp_path):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates["github"].pop("limits")
    candidates["github"]["g6"].append(
        {**candidates["github"]["g6"][0], "full_name": "acme/third-tool"}
    )
    _save(case, "candidates.json", candidates)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] candidates: github.g6 has 3 items" in result.stderr
    assert "github.limits.g6 is 2" in result.stderr


def test_a_repo_without_a_language_is_valid(cli, tmp_path):
    case = _case(tmp_path)
    candidates = _load(case, "candidates.json")
    candidates["github"]["new"][0]["language"] = ""
    _save(case, "candidates.json", candidates)

    digest = _digest(case).replace(
        "- **acme/cell-atlas** ⭐ 42 · Python ·",
        "- **acme/cell-atlas** ⭐ 42 · — ·",
    )
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 0, result.stderr


def test_a_release_requires_its_update_notes(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(
        case,
        _digest(case).replace(" · 细胞类型注释更快，修复批次效应边", ""),
    )

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: release acme/aging-atlas v0.3.0 is missing its 更新要点" in result.stderr


def test_an_active_repo_must_cite_its_last_push_not_its_creation_date(cli, tmp_path):
    case = _case(tmp_path)
    digest = "\n".join(
        line.replace("2026-10-21", "2024-01-01")
        if line.startswith("- **acme/scanpy-plus**")
        else line
        for line in _digest(case).split("\n")
    )
    _write_digest(case, digest)

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: GitHub item acme/scanpy-plus is missing its 最近更新 date" in result.stderr


def test_source_coverage_must_sit_on_the_source_line(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(
        case,
        _digest(case).replace(
            "来源：pubmed ok (2) ｜ europepmc ok (9) ｜ github ok (5)\n"
            "候选：12 ｜ 入选：10 ｜ 生成：2026-10-22T08:00:00+08:00",
            "来源：\n"
            "候选：12 ｜ 入选：10 ｜ 生成：2026-10-22T08:00:00+08:00\n"
            "pubmed ok (2) ｜ europepmc ok (9) ｜ github ok (5)",
        ),
    )

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: footer 来源： does not report pubmed ok" in result.stderr


def test_an_unknown_section_is_rejected(cli, tmp_path):
    case = _case(tmp_path)
    _write_digest(
        case,
        _digest(case).replace("\n---\n", "\n## 趋势\n- 本周新趋势\n\n---\n", 1),
    )

    result = run_digest(cli, case)

    assert result.returncode == 1
    assert "[fail] digest: unknown section: 趋势" in result.stderr


def test_non_g6_papers_cannot_all_be_parked_in_quick_scan(cli):
    result = run_digest(cli, FIXTURES / "digest" / "g6-quick-only")

    assert result.returncode == 1
    assert "[fail] selection: must_read has 0 papers, expected 2" in result.stderr
