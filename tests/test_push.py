import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES, NOW, run_push

VALID = FIXTURES / "digest" / "valid"
EMPTY = FIXTURES / "digest" / "empty"
PUSH_FIXTURES = FIXTURES / "push"

OMIT = object()


def _case(tmp_path, source=VALID, name="case"):
    case = tmp_path / name
    shutil.copytree(source, case)
    return case


def _config(tmp_path, push=OMIT, state_db=None):
    """A minimal valid config; ``push`` is omitted by default so defaults apply."""

    data = {
        "timezone": "Asia/Shanghai",
        "lookback": {"pubmed": 2},
        "topics": [
            {"name": "G1", "label": "老化", "terms": ["aging"], "max_items": 6},
            {"name": "G2", "label": "单细胞", "terms": ["single-cell"], "max_items": 4},
        ],
        "sources": {"pubmed": True},
        "paths": {"state_db": str(state_db or tmp_path / "state.sqlite3")},
    }
    if push is not OMIT:
        data["push"] = push
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _state(tmp_path):
    return tmp_path / "state.sqlite3"


def _payload(result):
    return json.loads(result.stdout)


def _desp_without_title(case):
    text = (Path(case) / "digest.md").read_text(encoding="utf-8")
    return text.split("\n", 1)[1].strip("\n").rstrip()


def test_dry_run_builds_one_serverchan_message(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path),
        dry_run=True,
        state_db=_state(tmp_path),
        env={"SERVERCHAN_SENDKEY": "sctp123tSECRETKEY"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = _payload(result)
    assert payload["schema_version"] == 1
    assert len(payload["messages"]) == 1
    message = payload["messages"][0]
    assert message["part"] == 1
    assert message["parts"] == 1
    assert message["title"] == "学术速递 · 2026-10-22"
    assert message["desp"] == _desp_without_title(case)
    assert message["desp"].startswith("> 关键词：")
    assert message["desp"].rstrip().endswith("生成：2026-10-22T08:00:00+08:00")
    assert "sctp" not in result.stdout
    assert "sctp" not in result.stderr
    # dry-run never opens the state database
    assert not _state(tmp_path).exists()


def test_dry_run_empty_digest_prints_the_notice_by_default(cli, tmp_path):
    case = _case(tmp_path, EMPTY)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    payload = _payload(result)
    assert "skipped" not in payload
    assert len(payload["messages"]) == 1
    desp = payload["messages"][0]["desp"]
    assert desp.startswith("今日没有匹配的检索条目\n\n---\n来源：pubmed ok (0)")
    assert "候选：0 ｜ 入选：0 ｜ 生成：" in desp


def test_dry_run_empty_digest_can_skip_sending(cli, tmp_path):
    case = _case(tmp_path, EMPTY)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"send_empty": False}),
        dry_run=True,
    )

    assert result.returncode == 0, result.stderr
    assert _payload(result) == {
        "schema_version": 1,
        "messages": [],
        "skipped": "empty",
    }


MUST_READ_TITLES = (
    "Aging multi-omics atlas of the mouse brain",
    "Single-cell foundation model benchmark",
    "Large language model agents for pathway reasoning",
)


def _section_span(text, name):
    start = text.index(f"## {name}")
    footer = text.find("\n---\n", start + 1)
    following = text.find("\n## ", start + 1)
    end = len(text)
    if following != -1:
        end = following
    if footer != -1 and footer < end:
        end = footer
    return start, end


def _pad_section(case, name, target_bytes):
    """Grow one digest section to at least ``target_bytes`` with filler text."""

    path = Path(case) / "digest.md"
    text = path.read_text(encoding="utf-8")
    start, end = _section_span(text, name)
    need = target_bytes - len(text[start:end].encode("utf-8"))
    assert need > 0, f"{name} is already {target_bytes} bytes"
    filler = "x" * need
    if name == "今日必读":
        line_end = text.index("\n", text.index("- 摘要：", start))
        text = text[:line_end] + "\n" + filler + text[line_end:]
    elif name == "其它速览":
        line_start = text.index("\n", start) + 1
        line_end = text.index("\n", line_start)
        insert = text.index(" · 局限性：", line_start)
        assert insert < line_end
        text = text[:insert] + " " + filler + text[insert:]
    else:
        line_start = text.index("\n- ", start) + 1
        line_end = text.index("\n", line_start)
        insert = text.rindex(" · [链接]", line_start, line_end)
        text = text[:insert] + " " + filler + text[insert:]
    path.write_text(text, encoding="utf-8")


def _body_text(case):
    lines = (Path(case) / "digest.md").read_text(encoding="utf-8").split("\n")
    first = next(index for index, line in enumerate(lines) if line.strip())
    body_lines = lines[first + 1 :]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    return "\n".join(body_lines).rstrip()


def _body_bytes(case):
    return len(_body_text(case).encode("utf-8"))


def _pad_body(case, target):
    """Grow the digest body to exactly ``target`` UTF-8 bytes."""

    path = Path(case) / "digest.md"
    need = target - _body_bytes(case)
    assert need > 0, f"body is already {target} bytes"
    filler = "x" * (need - 1)
    text = path.read_text(encoding="utf-8")
    line_end = text.index("\n", text.index("- 摘要："))
    path.write_text(
        text[:line_end] + "\n" + filler + text[line_end:], encoding="utf-8"
    )
    assert _body_bytes(case) == target


def _remove_preface(case):
    path = Path(case) / "digest.md"
    path.write_text(
        "\n".join(
            line
            for line in path.read_text(encoding="utf-8").split("\n")
            if not line.startswith("> 关键词：")
        ),
        encoding="utf-8",
    )


def test_dry_run_splits_a_long_digest_at_section_boundaries(cli, tmp_path):
    case = _case(tmp_path)
    _pad_section(case, "今日必读", 31500)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    messages = _payload(result)["messages"]
    assert [message["part"] for message in messages] == [1, 2]
    assert {message["parts"] for message in messages} == {2}
    assert messages[0]["title"] == "学术速递 · 2026-10-22（1/2）"
    assert messages[1]["title"] == "学术速递 · 2026-10-22（2/2）"
    for message in messages:
        assert len(message["title"]) <= 32
        assert len(message["desp"].encode("utf-8")) <= 32768
    assert messages[0]["desp"].startswith("> 关键词：")
    assert "## 今日必读" in messages[0]["desp"]
    assert "## 今日必读" not in messages[1]["desp"]
    for title in MUST_READ_TITLES:
        assert title in messages[0]["desp"]
        assert title not in messages[1]["desp"]
    assert "## 其它速览" not in messages[0]["desp"]
    assert "生成：" not in messages[0]["desp"]
    assert "未推送数：" not in messages[0]["desp"]
    for section in ("## 其它速览", "## GitHub", "## AI 工具 / Agent Harness"):
        assert section in messages[1]["desp"]
    assert messages[1]["desp"].rstrip().endswith(
        "生成：2026-10-22T08:00:00+08:00"
    )


def test_a_section_larger_than_the_byte_limit_fails(cli, tmp_path):
    case = _case(tmp_path)
    _pad_section(case, "今日必读", 33000)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 1
    assert "[fail] push:" in result.stderr
    assert "## 今日必读" in result.stderr
    assert "max_bytes" in result.stderr
    assert result.stdout == ""


def test_a_digest_that_needs_more_than_two_messages_fails(cli, tmp_path):
    case = _case(tmp_path)
    _pad_section(case, "今日必读", 20000)
    _pad_section(case, "其它速览", 20000)
    _pad_section(case, "GitHub", 20000)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 1
    assert "[fail] push:" in result.stderr
    assert "max_messages" in result.stderr


def test_a_split_title_must_still_fit_the_character_limit(cli, tmp_path):
    case = _case(tmp_path)
    _pad_section(case, "今日必读", 31500)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"title_max": 20}),
        dry_run=True,
    )

    assert result.returncode == 2
    assert "[fail] push:" in result.stderr
    assert "title_max" in result.stderr


def test_a_title_over_the_character_limit_fails(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli, case, config=_config(tmp_path, {"title_max": 5}), dry_run=True
    )

    assert result.returncode == 2
    assert "title_max" in result.stderr


def test_a_body_over_split_bytes_is_split_even_when_one_packet_would_fit(
    cli, tmp_path
):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"split_bytes": 100}),
        dry_run=True,
    )

    assert result.returncode == 0, result.stderr
    messages = _payload(result)["messages"]
    assert [message["parts"] for message in messages] == [2, 2]
    assert messages[0]["title"] == "学术速递 · 2026-10-22（1/2）"
    assert messages[1]["title"] == "学术速递 · 2026-10-22（2/2）"
    assert messages[1]["desp"].rstrip().endswith(
        "生成：2026-10-22T08:00:00+08:00"
    )


def test_split_bytes_may_not_exceed_max_bytes(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"split_bytes": 40000}),
        dry_run=True,
    )

    assert result.returncode == 2
    assert "[fail] push.split_bytes" in result.stderr


def test_only_the_serverchan_channel_is_supported(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"channel": "email"}),
        dry_run=True,
    )

    assert result.returncode == 2
    assert "[fail] push.channel" in result.stderr
    assert "serverchan" in result.stderr


def test_retries_must_not_be_negative(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"retries": -1}),
        dry_run=True,
    )

    assert result.returncode == 2
    assert "[fail] push.retries" in result.stderr


OK = PUSH_FIXTURES / "ok"
FAIL = PUSH_FIXTURES / "fail"


def _shift_case_date(case, new_date):
    for name in ("candidates.json", "selection.json", "digest.md"):
        path = Path(case) / name
        path.write_text(
            path.read_text(encoding="utf-8").replace("2026-10-22", new_date),
            encoding="utf-8",
        )


def _connect(tmp_path):
    return sqlite3.connect(_state(tmp_path))


def _run_rows(connection):
    return connection.execute(
        "SELECT status, command, sources_json, candidate_count, selected_count, "
        "pushed_count, pending_count, error FROM runs ORDER BY id"
    ).fetchall()


def _pending_rows(connection):
    return connection.execute(
        "SELECT part, parts, title, attempts, last_error, items_json "
        "FROM pending ORDER BY digest_date, part"
    ).fetchall()


def test_live_push_records_the_run_and_every_pushed_paper(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(cli, case, config=_config(tmp_path), fixtures=OK)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == "[ok] push: sent 1 message(s), recorded 10 paper(s)\n"
    connection = _connect(tmp_path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert _run_rows(connection) == [
            ("ok", "push", "{}", 12, 10, 10, 0, "")
        ]
        selection = json.loads(
            (VALID / "selection.json").read_text(encoding="utf-8")
        )
        expected = sorted(
            (paper["id"], paper["group"]) for paper in selection["papers"]
        )
        pushes = connection.execute(
            "SELECT item_id, topic, channel, digest_date, pushed_at FROM pushes"
        ).fetchall()
        assert sorted((row[0], row[1]) for row in pushes) == expected
        assert {row[2] for row in pushes} == {"serverchan"}
        assert {row[3] for row in pushes} == {"2026-10-22"}
        assert {row[4] for row in pushes} == {NOW}
        assert _pending_rows(connection) == []
    finally:
        connection.close()


def test_a_second_push_does_not_duplicate_pushes(cli, tmp_path):
    case = _case(tmp_path)
    config = _config(tmp_path)
    first = run_push(cli, case, config=config, fixtures=OK)
    assert first.returncode == 0, first.stderr

    second = run_push(cli, case, config=config, fixtures=OK)

    assert second.returncode == 0, second.stderr
    assert second.stdout == "[ok] push: sent 1 message(s), recorded 0 paper(s)\n"
    connection = _connect(tmp_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM pushes").fetchone()[0] == 10
        assert [row[5] for row in _run_rows(connection)] == [10, 0]
    finally:
        connection.close()


def test_live_push_requires_a_sendkey_and_does_not_open_the_state(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path),
        env={"SERVERCHAN_SENDKEY": ""},
    )

    assert result.returncode == 2
    assert "[fail] push: SERVERCHAN_SENDKEY is not set" in result.stderr
    assert not _state(tmp_path).exists()


def test_sendkey_env_names_the_environment_variable(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"sendkey_env": "ACADEMIC_TEST_KEY"}),
        env={"ACADEMIC_TEST_KEY": "", "SERVERCHAN_SENDKEY": "sctp1tvalue"},
    )

    assert result.returncode == 2
    assert "ACADEMIC_TEST_KEY is not set" in result.stderr


def test_a_failed_send_retries_then_writes_pending(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path),
        fixtures=FAIL,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "[fail] push: message 1/1: ServerChan code 1" in result.stderr
    connection = _connect(tmp_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM pushes").fetchone()[0] == 0
        pending = _pending_rows(connection)
        assert len(pending) == 1
        part, parts, title, attempts, last_error, items_json = pending[0]
        assert (part, parts) == (1, 1)
        assert title == "学术速递 · 2026-10-22"
        assert attempts == 3
        assert "ServerChan code 1" in last_error
        assert len(json.loads(items_json)) == 10
        runs = _run_rows(connection)
        assert len(runs) == 1
        status, command, sources, candidates, selected, pushed, waiting, error = runs[0]
        assert (status, command, sources, candidates, selected, pushed, waiting) == (
            "failed",
            "push",
            "{}",
            12,
            10,
            0,
            1,
        )
        assert "message 1/1" in error
    finally:
        connection.close()


def test_a_missing_fixture_response_counts_as_a_transport_failure(cli, tmp_path):
    case = _case(tmp_path)
    empty = tmp_path / "no-responses"
    empty.mkdir()

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"retries": 2, "backoff_seconds": 0}),
        fixtures=empty,
    )

    assert result.returncode == 1
    connection = _connect(tmp_path)
    try:
        attempts, last_error = connection.execute(
            "SELECT attempts, last_error FROM pending"
        ).fetchone()
        assert attempts == 3
        assert "missing ServerChan fixture" in last_error
    finally:
        connection.close()


def test_retries_can_be_disabled(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"retries": 0}),
        fixtures=FAIL,
    )

    assert result.returncode == 1
    connection = _connect(tmp_path)
    try:
        assert connection.execute("SELECT attempts FROM pending").fetchone()[0] == 1
    finally:
        connection.close()


def test_a_non_2xx_response_is_a_failure(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"retries": 0}),
        fixtures=PUSH_FIXTURES / "http-500",
    )

    assert result.returncode == 1
    connection = _connect(tmp_path)
    try:
        assert "HTTP 500" in connection.execute(
            "SELECT last_error FROM pending"
        ).fetchone()[0]
    finally:
        connection.close()


def test_a_non_json_response_is_a_failure(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"retries": 0}),
        fixtures=PUSH_FIXTURES / "non-json",
    )

    assert result.returncode == 1
    connection = _connect(tmp_path)
    try:
        assert "not JSON" in connection.execute(
            "SELECT last_error FROM pending"
        ).fetchone()[0]
    finally:
        connection.close()


def _two_part_case(tmp_path):
    case = _case(tmp_path, name="day1")
    _pad_section(case, "今日必读", 31500)
    return case


def test_pending_is_retried_before_the_new_digest(cli, tmp_path):
    day1 = _two_part_case(tmp_path)
    config = _config(tmp_path)
    first = run_push(
        cli,
        day1,
        config=config,
        fixtures=FAIL,
    )
    assert first.returncode == 1, first.stderr
    connection = _connect(tmp_path)
    try:
        assert [(row[0], row[3]) for row in _pending_rows(connection)] == [
            (1, 3),
            (2, 0),
        ]
    finally:
        connection.close()

    day2 = _case(tmp_path, name="day2")
    _shift_case_date(day2, "2026-10-23")
    second = run_push(
        cli,
        day2,
        config=config,
        fixtures=OK,
        now="2026-10-23T08:00:00+08:00",
    )

    assert second.returncode == 0, second.stderr
    assert second.stdout == "[ok] push: sent 3 message(s), recorded 20 paper(s)\n"
    connection = _connect(tmp_path)
    try:
        assert _pending_rows(connection) == []
        by_date = connection.execute(
            "SELECT digest_date, COUNT(*) FROM pushes GROUP BY digest_date "
            "ORDER BY digest_date"
        ).fetchall()
        assert by_date == [("2026-10-22", 10), ("2026-10-23", 10)]
        latest = _run_rows(connection)[-1]
        assert latest[0] == "ok"
        assert latest[5] == 20
        assert latest[6] == 0
    finally:
        connection.close()


def test_a_failed_pending_part_does_not_block_the_new_digest(cli, tmp_path):
    day1 = _two_part_case(tmp_path)
    config = _config(tmp_path)
    first = run_push(cli, day1, config=config, fixtures=FAIL)
    assert first.returncode == 1

    day2 = _case(tmp_path, name="day2")
    _shift_case_date(day2, "2026-10-23")
    second = run_push(
        cli,
        day2,
        config=config,
        fixtures=PUSH_FIXTURES / "partial",
        now="2026-10-23T08:00:00+08:00",
    )

    assert second.returncode == 0, second.stderr
    assert second.stdout == "[ok] push: sent 2 message(s), recorded 10 paper(s)\n"
    connection = _connect(tmp_path)
    try:
        pending = _pending_rows(connection)
        assert len(pending) == 1
        assert (pending[0][0], pending[0][1], pending[0][3]) == (1, 2, 4)
        assert "ServerChan code 1" in pending[0][4]
        assert connection.execute(
            "SELECT digest_date, COUNT(*) FROM pushes GROUP BY digest_date"
        ).fetchall() == [("2026-10-23", 10)]
        latest = _run_rows(connection)[-1]
        assert latest[0] == "ok"
        assert latest[5] == 10
        assert latest[6] == 1
        assert "pending 2026-10-22 part 1/2" in latest[7]
    finally:
        connection.close()


def test_pending_older_than_two_days_is_dropped(cli, tmp_path):
    day1 = _case(tmp_path, name="day1")
    config = _config(tmp_path, {"retries": 0, "backoff_seconds": 0})
    first = run_push(cli, day1, config=config, fixtures=FAIL)
    assert first.returncode == 1

    empty = _case(tmp_path, EMPTY, name="empty")
    config = _config(tmp_path, {"send_empty": False})
    no_responses = tmp_path / "no-responses"
    no_responses.mkdir()
    second = run_push(
        cli,
        empty,
        config=config,
        fixtures=no_responses,
        now="2026-10-25T08:00:00+08:00",
    )

    assert second.returncode == 0, second.stderr
    assert second.stdout == "[ok] push: skipped empty digest\n"
    connection = _connect(tmp_path)
    try:
        assert _pending_rows(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM pushes").fetchone()[0] == 0
        latest = _run_rows(connection)[-1]
        assert latest[0] == "skipped_empty"
        assert latest[6] == 0
        assert "dropped 1 pending digest(s) older than 2 days" in latest[7]
        assert "2026-10-22" in latest[7]
    finally:
        connection.close()


def test_pending_at_two_days_old_is_still_retried(cli, tmp_path):
    day1 = _case(tmp_path, name="day1")
    config = _config(tmp_path, {"retries": 0, "backoff_seconds": 0})
    first = run_push(cli, day1, config=config, fixtures=FAIL)
    assert first.returncode == 1

    empty = _case(tmp_path, EMPTY, name="empty")
    config = _config(tmp_path, {"send_empty": False})
    no_responses = tmp_path / "no-responses"
    no_responses.mkdir()
    second = run_push(
        cli,
        empty,
        config=config,
        fixtures=no_responses,
        now="2026-10-24T08:00:00+08:00",
    )

    assert second.returncode == 1
    assert "[fail] push:" in second.stderr
    connection = _connect(tmp_path)
    try:
        pending = _pending_rows(connection)
        assert len(pending) == 1
        assert pending[0][3] == 2
        latest = _run_rows(connection)[-1]
        assert latest[0] == "failed"
        assert latest[6] == 1
    finally:
        connection.close()


def test_an_empty_digest_is_skipped_when_send_empty_is_false(cli, tmp_path):
    empty = _case(tmp_path, EMPTY)
    no_responses = tmp_path / "no-responses"
    no_responses.mkdir()

    result = run_push(
        cli,
        empty,
        config=_config(tmp_path, {"send_empty": False}),
        fixtures=no_responses,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[ok] push: skipped empty digest\n"
    connection = _connect(tmp_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM pushes").fetchone()[0] == 0
        assert _pending_rows(connection) == []
        assert _run_rows(connection)[0][0] == "skipped_empty"
    finally:
        connection.close()


def test_an_empty_digest_sends_one_notice_message_by_default(cli, tmp_path):
    empty = _case(tmp_path, EMPTY)

    result = run_push(cli, empty, config=_config(tmp_path), fixtures=OK)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[ok] push: sent 1 message(s), recorded 0 paper(s)\n"
    connection = _connect(tmp_path)
    try:
        assert _run_rows(connection)[0][:1] == ("ok",)
        assert connection.execute("SELECT COUNT(*) FROM pushes").fetchone()[0] == 0
        assert _pending_rows(connection) == []
    finally:
        connection.close()


def test_a_failed_empty_notice_is_a_failure_without_pending(cli, tmp_path):
    empty = _case(tmp_path, EMPTY)

    result = run_push(
        cli,
        empty,
        config=_config(tmp_path, {"retries": 0}),
        fixtures=FAIL,
    )

    assert result.returncode == 1
    assert "[fail] push: message 1/1: ServerChan code 1" in result.stderr
    connection = _connect(tmp_path)
    try:
        assert _pending_rows(connection) == []
        latest = _run_rows(connection)[0]
        assert latest[0] == "failed"
        assert latest[6] == 0
    finally:
        connection.close()


def test_a_split_digest_sends_every_message(cli, tmp_path):
    case = _two_part_case(tmp_path)

    result = run_push(cli, case, config=_config(tmp_path), fixtures=OK)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[ok] push: sent 2 message(s), recorded 10 paper(s)\n"


def test_the_runs_table_migrates_from_schema_two(cli, tmp_path):
    database = _state(tmp_path)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                command TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO runs
                (started_at, finished_at, status, command, sources_json,
                 candidate_count)
            VALUES ('2026-10-21T08:00:00+08:00', '2026-10-21T08:00:01+08:00',
                    'ok', 'collect', '{}', 3);
            PRAGMA user_version = 2;
            """
        )
        connection.commit()
    finally:
        connection.close()

    result = run_push(cli, _case(tmp_path), config=_config(tmp_path), fixtures=OK)

    assert result.returncode == 0, result.stderr
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(runs)")
        ]
        for column in ("selected_count", "pushed_count", "pending_count"):
            assert column in columns
        old = connection.execute(
            "SELECT selected_count, pushed_count, pending_count FROM runs "
            "WHERE command = 'collect'"
        ).fetchone()
        assert old == (0, 0, 0)
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM pending"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_an_invalid_selection_is_not_sent_and_writes_no_state(cli, tmp_path):
    case = _case(tmp_path)
    selection = json.loads(
        (case / "selection.json").read_text(encoding="utf-8")
    )
    selection["papers"][0]["id"] = "doi:10.1000/not-in-pool"
    (case / "selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = run_push(cli, case, config=_config(tmp_path), fixtures=OK)

    assert result.returncode == 1
    assert "[fail] selection:" in result.stderr
    assert "is not in candidates.papers" in result.stderr
    assert not _state(tmp_path).exists()


def test_out_is_only_valid_with_dry_run(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path),
        out=tmp_path / "payload.json",
    )

    assert result.returncode == 2
    assert "--out can only be used with --dry-run" in result.stderr
    assert not (tmp_path / "payload.json").exists()


def test_dry_run_writes_the_payload_to_out(cli, tmp_path):
    case = _case(tmp_path)
    out = tmp_path / "payload.json"

    result = run_push(
        cli, case, config=_config(tmp_path), dry_run=True, out=out
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["messages"][0]["title"] == "学术速递 · 2026-10-22"


def test_a_state_path_that_cannot_be_opened_fails_before_sending(cli, tmp_path):
    case = _case(tmp_path)
    database = _state(tmp_path)
    database.mkdir()

    result = run_push(
        cli,
        case,
        config=_config(tmp_path),
        fixtures=OK,
    )

    assert result.returncode == 1
    assert "[fail] push: cannot open or write the state database" in result.stderr


def test_the_sendkey_never_reaches_output_or_state(cli, tmp_path):
    case = _case(tmp_path)
    key = "sctp98765tVERYSECRETKEY"

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"retries": 0}),
        fixtures=FAIL,
        env={"SERVERCHAN_SENDKEY": key},
    )

    assert result.returncode == 1
    assert key not in result.stdout
    assert key not in result.stderr
    assert "sctp" not in result.stdout
    assert "sctp" not in result.stderr
    assert key.encode() not in _state(tmp_path).read_bytes()


def test_a_pending_only_run_is_ok_and_records_its_papers(cli, tmp_path):
    day1 = _case(tmp_path, name="day1")
    config = _config(tmp_path, {"retries": 0})
    first = run_push(cli, day1, config=config, fixtures=FAIL)
    assert first.returncode == 1

    empty = _case(tmp_path, EMPTY, name="empty")
    config = _config(tmp_path, {"send_empty": False})
    second = run_push(cli, empty, config=config, fixtures=OK)

    assert second.returncode == 0, second.stderr
    assert second.stdout == "[ok] push: sent 1 message(s), recorded 10 paper(s)\n"
    connection = _connect(tmp_path)
    try:
        assert _pending_rows(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM pushes").fetchone()[0] == 10
        latest = _run_rows(connection)[-1]
        assert latest[0] == "ok"
        assert latest[5] == 10
        assert latest[6] == 0
    finally:
        connection.close()


def test_the_unpushed_count_goes_into_the_last_message_footer(cli, tmp_path):
    day1 = _case(tmp_path, name="day1")
    config = _config(tmp_path, {"retries": 0})
    first = run_push(cli, day1, config=config, fixtures=FAIL)
    assert first.returncode == 1

    day2 = _case(tmp_path, name="day2")
    _shift_case_date(day2, "2026-10-23")
    second = run_push(
        cli,
        day2,
        config=config,
        fixtures=FAIL,
        now="2026-10-23T08:00:00+08:00",
    )

    assert second.returncode == 1
    connection = _connect(tmp_path)
    try:
        pending = _pending_rows(connection)
        assert [row[0] for row in pending] == [1, 1]
        desp = connection.execute(
            "SELECT desp FROM pending WHERE digest_date = '2026-10-23'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert desp.rstrip().endswith("未推送数：1")
    assert "生成：2026-10-23T08:00:00+08:00" in desp


def test_a_live_title_over_the_limit_writes_a_failed_run(cli, tmp_path):
    case = _case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"title_max": 5}),
        fixtures=OK,
    )

    assert result.returncode == 2
    assert "title_max" in result.stderr
    connection = _connect(tmp_path)
    try:
        runs = _run_rows(connection)
        assert len(runs) == 1
        assert runs[0][0] == "failed"
        assert "title_max" in runs[0][7]
        assert _pending_rows(connection) == []
    finally:
        connection.close()


def test_an_invalid_digest_is_not_sent_and_writes_no_state(cli, tmp_path):
    case = _case(tmp_path)
    text = (case / "digest.md").read_text(encoding="utf-8")
    (case / "digest.md").write_text(
        "\n".join(
            line
            for line in text.split("\n")
            if not line.startswith("- **Plasma proteomics")
        ),
        encoding="utf-8",
    )

    result = run_push(cli, case, config=_config(tmp_path), fixtures=OK)

    assert result.returncode == 1
    assert "[fail] digest:" in result.stderr
    assert not _state(tmp_path).exists()


def test_a_failed_pushes_write_is_not_retried_as_pending(cli, tmp_path):
    database = _state(tmp_path)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE pushes (x TEXT)")
        connection.commit()
    finally:
        connection.close()

    result = run_push(cli, _case(tmp_path), config=_config(tmp_path), fixtures=OK)

    assert result.returncode == 1
    assert "[fail] push:" in result.stderr
    assert "state database" in result.stderr
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM pending").fetchone()[0] == 0
        latest = _run_rows(connection)[-1]
        assert latest[0] == "failed"
    finally:
        connection.close()


def test_state_db_can_be_overridden(cli, tmp_path):
    case = _case(tmp_path)
    other = tmp_path / "other.sqlite3"

    result = run_push(
        cli,
        case,
        config=_config(tmp_path),
        fixtures=OK,
        state_db=other,
    )

    assert result.returncode == 0, result.stderr
    assert other.exists()
    assert not _state(tmp_path).exists()


def test_pending_pushes_are_counted_even_when_the_new_digest_fails(cli, tmp_path):
    day1 = _case(tmp_path, name="day1")
    config = _config(tmp_path, {"retries": 0})
    first = run_push(cli, day1, config=config, fixtures=FAIL)
    assert first.returncode == 1

    day2 = _case(tmp_path, name="day2")
    _shift_case_date(day2, "2026-10-23")
    second = run_push(
        cli,
        day2,
        config=config,
        fixtures=PUSH_FIXTURES / "pending-ok-current-fail",
        now="2026-10-23T08:00:00+08:00",
    )

    assert second.returncode == 1
    connection = _connect(tmp_path)
    try:
        pending = _pending_rows(connection)
        assert len(pending) == 1
        assert connection.execute(
            "SELECT digest_date FROM pending"
        ).fetchone()[0] == "2026-10-23"
        latest = _run_rows(connection)[-1]
        assert latest[0] == "failed"
        assert latest[5] == 10
        assert latest[6] == 1
    finally:
        connection.close()


def _set_digest_date(case, value):
    for name in ("candidates.json", "selection.json"):
        path = Path(case) / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data["date"] = value
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    path = Path(case) / "digest.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    lines[0] = f"# 学术速递 · {value}"
    path.write_text("\n".join(lines), encoding="utf-8")


def test_the_default_title_limit_is_32_characters(cli, tmp_path):
    case = _case(tmp_path)
    # "学术速递 · " is 7 characters, so this title is exactly 32.
    date = "2026-10-22T08:00:00+08:00"
    _set_digest_date(case, date)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    assert len(_payload(result)["messages"][0]["title"]) == 32

    _set_digest_date(case, date + "x")
    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 2
    assert "title_max" in result.stderr


@pytest.mark.parametrize(
    ("push", "field"),
    [
        ({"sendkey_env": ""}, "push.sendkey_env"),
        ({"send_empty": "yes"}, "push.send_empty"),
        ({"split_bytes": 0}, "push.split_bytes"),
        ({"max_bytes": 0}, "push.max_bytes"),
        ({"max_messages": 0}, "push.max_messages"),
        ({"title_max": 0}, "push.title_max"),
        ({"timeout": 0}, "push.timeout"),
        ({"pending_days": 0}, "push.pending_days"),
        ({"backoff_seconds": -1}, "push.backoff_seconds"),
        ({"unknown": 1}, "push.unknown"),
    ],
)
def test_a_bad_push_config_reports_the_field(cli, tmp_path, push, field):
    case = _case(tmp_path)

    result = run_push(cli, case, config=_config(tmp_path, push), dry_run=True)

    assert result.returncode == 2
    assert f"[fail] {field}" in result.stderr


MUST_READ_ONLY = FIXTURES / "digest" / "must-read-only"


def test_a_one_section_digest_is_still_split_over_the_threshold(cli, tmp_path):
    case = _case(tmp_path, MUST_READ_ONLY)
    _pad_section(case, "今日必读", 31000)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    messages = _payload(result)["messages"]
    assert [message["part"] for message in messages] == [1, 2]
    assert {message["parts"] for message in messages} == {2}
    assert messages[0]["desp"].startswith("> 关键词：")
    assert "## 今日必读" not in messages[0]["desp"]
    assert "## 今日必读" in messages[1]["desp"]
    assert messages[1]["desp"].rstrip().endswith(
        "生成：2026-10-22T08:00:00+08:00"
    )
    for message in messages:
        assert len(message["desp"].encode("utf-8")) <= 32768


def test_a_single_section_without_a_preface_cannot_be_split(cli, tmp_path):
    case = _case(tmp_path, MUST_READ_ONLY)
    _remove_preface(case)
    _pad_body(case, 31000)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 1
    assert "no top-level section boundary" in result.stderr


def test_the_default_split_threshold_is_30000_bytes(cli, tmp_path):
    at_limit = _case(tmp_path, MUST_READ_ONLY, name="at-limit")
    _pad_body(at_limit, 30000)

    result = run_push(cli, at_limit, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    messages = _payload(result)["messages"]
    assert len(messages) == 1
    assert len(messages[0]["desp"].encode("utf-8")) == 30000

    over = _case(tmp_path, MUST_READ_ONLY, name="over")
    _pad_body(over, 30001)
    result = run_push(cli, over, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    messages = _payload(result)["messages"]
    assert [message["part"] for message in messages] == [1, 2]


def test_a_body_at_the_default_max_bytes_is_sendable(cli, tmp_path):
    case = _case(tmp_path, MUST_READ_ONLY, name="max-at-limit")
    _pad_body(case, 32768)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    messages = _payload(result)["messages"]
    assert [message["part"] for message in messages] == [1, 2]
    for message in messages:
        assert len(message["desp"].encode("utf-8")) <= 32768


def test_the_default_max_bytes_is_32768(cli, tmp_path):
    case = _case(tmp_path, MUST_READ_ONLY, name="max-over")
    _pad_body(case, 33000)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 1
    assert "over push.max_bytes 32768" in result.stderr


def test_whitespace_only_preface_makes_no_empty_message(cli, tmp_path):
    case = _case(tmp_path, MUST_READ_ONLY)
    _pad_body(case, 31000)
    path = case / "digest.md"
    path.write_text(
        "\n".join(
            "    " if line.startswith("> 关键词：") else line
            for line in path.read_text(encoding="utf-8").split("\n")
        ),
        encoding="utf-8",
    )

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    # A whitespace-only preface is not a boundary: the body cannot be split,
    # so it fails instead of posting an empty first message.
    assert result.returncode == 1
    assert "no top-level section boundary" in result.stderr


GITHUB_ONLY = FIXTURES / "digest" / "github-only"


def test_github_items_make_a_digest_non_empty(cli, tmp_path):
    case = _case(tmp_path, GITHUB_ONLY)

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    payload = _payload(result)
    assert "skipped" not in payload
    messages = payload["messages"]
    assert len(messages) == 1
    assert "## GitHub" in messages[0]["desp"]
    assert "今日没有匹配的检索条目" not in messages[0]["desp"]

    skipped_case = _case(tmp_path, GITHUB_ONLY, name="github-only-2")
    result = run_push(
        cli,
        skipped_case,
        config=_config(tmp_path, {"send_empty": False}),
        dry_run=True,
    )

    assert result.returncode == 0, result.stderr
    payload = _payload(result)
    assert "skipped" not in payload
    assert len(payload["messages"]) == 1


def test_the_empty_notice_keeps_the_preface(cli, tmp_path):
    case = _case(tmp_path, EMPTY)
    path = case / "digest.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "# 学术速递 · 2026-10-22\n",
            "# 学术速递 · 2026-10-22\n> 关键词：老化、多组学\n\n",
            1,
        ),
        encoding="utf-8",
    )

    result = run_push(cli, case, config=_config(tmp_path), dry_run=True)

    assert result.returncode == 0, result.stderr
    desp = _payload(result)["messages"][0]["desp"]
    assert desp.startswith("> 关键词：老化、多组学")
    notice_at = desp.index("今日没有匹配的检索条目")
    footer_at = desp.index("\n---\n")
    assert desp.index("> 关键词") < notice_at < footer_at


def _seed_pending(
    connection,
    *,
    digest_date="2026-10-22",
    created_at="2026-10-22T08:00:00+08:00",
    title="学术速递 · 2026-10-22",
):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS pending (
            channel TEXT NOT NULL,
            digest_date TEXT NOT NULL,
            part INTEGER NOT NULL,
            parts INTEGER NOT NULL,
            title TEXT NOT NULL,
            desp TEXT NOT NULL,
            items_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (channel, digest_date, part)
        );
        """
    )
    connection.execute(
        "INSERT INTO pending (channel, digest_date, part, parts, title, desp, "
        "items_json, created_at, attempts, last_error) "
        "VALUES ('serverchan', ?, 1, 1, ?, 'old body', '[]', ?, 1, 'boom')",
        (digest_date, title, created_at),
    )
    connection.commit()


def test_pending_age_uses_created_at(cli, tmp_path):
    connection = _connect(tmp_path)
    try:
        _seed_pending(connection)
        connection.execute(
            "UPDATE pending SET created_at = '2026-10-19T08:00:00+08:00'"
        )
        connection.commit()
    finally:
        connection.close()

    empty = _case(tmp_path, EMPTY, name="empty")
    no_responses = tmp_path / "no-responses"
    no_responses.mkdir()
    result = run_push(
        cli,
        empty,
        config=_config(tmp_path, {"send_empty": False}),
        fixtures=no_responses,
        now="2026-10-24T08:00:00+08:00",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[ok] push: skipped empty digest\n"
    connection = _connect(tmp_path)
    try:
        assert _pending_rows(connection) == []
        assert "dropped 1 pending digest(s)" in _run_rows(connection)[-1][7]
    finally:
        connection.close()


def test_a_recent_pending_survives_an_old_digest_date(cli, tmp_path):
    connection = _connect(tmp_path)
    try:
        _seed_pending(connection)
        connection.execute(
            "UPDATE pending SET digest_date = '2026-10-19', "
            "created_at = '2026-10-24T23:00:00+08:00'"
        )
        connection.commit()
    finally:
        connection.close()

    empty = _case(tmp_path, EMPTY, name="empty")
    no_responses = tmp_path / "no-responses"
    no_responses.mkdir()
    result = run_push(
        cli,
        empty,
        config=_config(tmp_path, {"send_empty": False}),
        fixtures=no_responses,
        now="2026-10-25T08:00:00+08:00",
    )

    assert result.returncode == 1
    connection = _connect(tmp_path)
    try:
        pending = _pending_rows(connection)
        assert len(pending) == 1
        assert pending[0][3] == 2
        assert "dropped" not in _run_rows(connection)[-1][7]
    finally:
        connection.close()


def test_a_partial_current_digest_stores_only_the_unsent_parts(cli, tmp_path):
    case = _two_part_case(tmp_path)

    result = run_push(
        cli,
        case,
        config=_config(tmp_path, {"retries": 0}),
        fixtures=PUSH_FIXTURES / "pending-ok-current-fail",
    )

    assert result.returncode == 1
    assert "[fail] push: message 2/2: ServerChan code 1" in result.stderr
    connection = _connect(tmp_path)
    try:
        pending = _pending_rows(connection)
        assert len(pending) == 1
        part, parts, title, attempts, last_error, _ = pending[0]
        assert (part, parts) == (2, 2)
        assert title == "学术速递 · 2026-10-22（2/2）"
        assert attempts == 1
        assert "ServerChan code 1" in last_error
        assert connection.execute("SELECT COUNT(*) FROM pushes").fetchone()[0] == 0
        latest = _run_rows(connection)[-1]
        assert latest[0] == "failed"
        assert latest[5] == 0
        assert latest[6] == 1
    finally:
        connection.close()


def test_only_the_earliest_pending_group_is_retried(cli, tmp_path):
    connection = _connect(tmp_path)
    try:
        _seed_pending(
            connection,
            digest_date="2026-10-21",
            created_at="2026-10-21T08:00:00+08:00",
            title="学术速递 · 2026-10-21",
        )
        _seed_pending(
            connection,
            digest_date="2026-10-22",
            created_at="2026-10-22T08:00:00+08:00",
            title="学术速递 · 2026-10-22",
        )
    finally:
        connection.close()

    empty = _case(tmp_path, EMPTY, name="empty")
    result = run_push(
        cli,
        empty,
        config=_config(tmp_path, {"send_empty": False}),
        fixtures=OK,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[ok] push: sent 1 message(s), recorded 0 paper(s)\n"
    connection = _connect(tmp_path)
    try:
        pending = _pending_rows(connection)
        assert len(pending) == 1
        assert connection.execute(
            "SELECT digest_date, attempts FROM pending"
        ).fetchone() == ("2026-10-22", 1)
        latest = _run_rows(connection)[-1]
        assert latest[0] == "ok"
        assert latest[6] == 1
    finally:
        connection.close()
