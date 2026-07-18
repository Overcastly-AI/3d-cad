"""py_kit.logging — structured JSON output, console dev mode, request context."""

import json

import pytest
from py_kit.config import BaseServiceSettings
from py_kit.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)


@pytest.fixture(autouse=True)
def _clean_context() -> None:
    clear_request_context()


def _last_line(capsys: pytest.CaptureFixture[str]) -> str:
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert lines, "expected at least one log line on stdout"
    return lines[-1]


def test_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(BaseServiceSettings(service_name="documents"))
    get_logger("test").info("part_created", part_id="p1")

    record = json.loads(_last_line(capsys))
    assert record["event"] == "part_created"
    assert record["part_id"] == "p1"
    assert record["level"] == "info"
    assert record["service"] == "documents"
    assert "timestamp" in record


def test_log_level_filtering(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(BaseServiceSettings(log_level="WARNING"))
    logger = get_logger("test")
    logger.info("suppressed")
    logger.warning("emitted")

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    events = [json.loads(line)["event"] for line in lines]
    assert "suppressed" not in events
    assert "emitted" in events


def test_console_format_is_not_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(BaseServiceSettings(log_format="console"))
    get_logger("test").info("dev_line")

    line = _last_line(capsys)
    assert "dev_line" in line
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)


def test_request_context_binding(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(BaseServiceSettings())
    bind_request_context(request_id="req-42")
    get_logger("test").info("with_context")
    clear_request_context()
    get_logger("test").info("without_context")

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    bound, unbound = (json.loads(line) for line in lines[-2:])
    assert bound["request_id"] == "req-42"
    assert "request_id" not in unbound
