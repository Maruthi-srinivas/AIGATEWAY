from __future__ import annotations

import asyncio

from aiokafka import AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from aigateway.config import GatewaySettings
from aigateway.contracts import KAFKA_TOPICS, ChatEvent, kafka_dlq_topic
from aigateway.telemetry import correlation_id_var, get_logger

logger = get_logger(__name__)


def all_topic_names() -> list[str]:
    names = list(KAFKA_TOPICS)
    names.extend(kafka_dlq_topic(topic) for topic in KAFKA_TOPICS)
    return names


async def ensure_topics(bootstrap_servers: str, timeout_seconds: float) -> None:
    timeout_ms = int(timeout_seconds * 1000)
    admin = AIOKafkaAdminClient(
        bootstrap_servers=bootstrap_servers,
        request_timeout_ms=timeout_ms,
    )
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = [
            NewTopic(name=name, num_partitions=1, replication_factor=1)
            for name in all_topic_names()
            if name not in existing
        ]
        if not missing:
            return
        try:
            await admin.create_topics(missing)
        except TopicAlreadyExistsError:
            return
    finally:
        await admin.close()


def correlation_headers() -> list[tuple[str, bytes]] | None:
    cid = correlation_id_var.get()
    if not cid:
        return None
    return [("X-Correlation-ID", cid.encode("utf-8"))]


class KafkaEventPublisher:
    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        servers = self._settings.kafka_bootstrap_servers
        if not servers:
            return
        try:
            await ensure_topics(servers, 5.0)
            producer = AIOKafkaProducer(
                bootstrap_servers=servers,
                request_timeout_ms=5000,
                linger_ms=0,
            )
            await producer.start()
            self._producer = producer
        except Exception:
            logger.warning("kafka producer unavailable")
            self._producer = None

    async def stop(self) -> None:
        if self._producer is None:
            return
        await self._producer.stop()
        self._producer = None

    async def publish(self, event: ChatEvent) -> None:
        if self._producer is None:
            logger.warning("kafka publish skipped topic=%s", event.topic)
            return
        timeout = self._settings.kafka_publish_timeout_seconds
        try:
            payload = event.model_dump_json().encode("utf-8")
            await asyncio.wait_for(
                self._producer.send_and_wait(
                    event.topic,
                    payload,
                    headers=correlation_headers(),
                ),
                timeout=timeout,
            )
        except Exception:
            logger.warning("kafka publish failed topic=%s", event.topic)


class NullEventPublisher:
    async def publish(self, event: ChatEvent) -> None:
        _ = event
