import json
import logging

from aigateway.telemetry.logging import (
    JSONFormatter,
    correlation_id_var,
    tenant_id_var,
    user_id_var,
)


def test_json_formatter_includes_service_and_level() -> None:
    formatter = JSONFormatter("gateway")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["service"] == "gateway"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert "correlation_id" not in payload


def test_json_formatter_includes_correlation_id() -> None:
    formatter = JSONFormatter("gateway")
    token = correlation_id_var.set("cid-1")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="warn",
            args=(),
            exc_info=None,
        )
        payload = json.loads(formatter.format(record))
    finally:
        correlation_id_var.reset(token)
    assert payload["correlation_id"] == "cid-1"


def test_json_formatter_includes_user_and_tenant() -> None:
    formatter = JSONFormatter("gateway")
    t1 = user_id_var.set("user-1")
    t2 = tenant_id_var.set("tenant-a")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        payload = json.loads(formatter.format(record))
    finally:
        user_id_var.reset(t1)
        tenant_id_var.reset(t2)
    assert payload["user_id"] == "user-1"
    assert payload["tenant_id"] == "tenant-a"
