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


def test_audit_query_keeps_the_caller_tenant() -> None:
    from sqlalchemy.dialects import postgresql

    from aigateway.auth.audit import select_audit

    tenant = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    other = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    dialect = postgresql.dialect()
    matched = select_audit(tenant, "cid-1").compile(
        dialect=dialect,
        compile_kwargs={"literal_binds": True},
    )
    sql = str(matched)
    assert tenant in sql
    assert "cid-1" in sql
    assert other not in sql
    other_sql = str(
        select_audit(other, "cid-1").compile(
            dialect=dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    assert other in other_sql
    assert tenant not in other_sql


async def test_publish_sets_correlation_header() -> None:
    from aigateway.contracts import ChatEvent
    from aigateway.gateway.events import KafkaEventPublisher
    from aigateway.telemetry import correlation_id_var
    from tests.helpers import gateway_settings

    class FakeProducer:
        def __init__(self) -> None:
            self.sent: list[tuple[str, bytes, object]] = []

        async def send_and_wait(self, topic, payload, headers=None):
            self.sent.append((topic, payload, headers))

    publisher = KafkaEventPublisher(gateway_settings())
    producer = FakeProducer()
    publisher._producer = producer
    token = correlation_id_var.set("cid-header")
    try:
        await publisher.publish(
            ChatEvent(event_id="e1", correlation_id="cid-header", topic="ai.requests")
        )
    finally:
        correlation_id_var.reset(token)
    topic, payload, headers = producer.sent[0]
    assert topic == "ai.requests"
    assert headers == [("X-Correlation-ID", b"cid-header")]
    assert b"cid-header" in payload
    assert b"prompt" not in payload
