from __future__ import annotations

import asyncio
import secrets
from collections import Counter

import redis.asyncio as redis
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from aigateway.config import WorkerSettings
from aigateway.contracts import KAFKA_TOPICS, ChatEvent, kafka_dlq_topic
from aigateway.telemetry import correlation_id_var, get_logger, span

logger = get_logger(__name__)

GROUP_ID = "aigateway-analytics"
MAX_ATTEMPTS = 3


class AnalyticsConsumer:
    def __init__(self, settings: WorkerSettings) -> None:
        self._settings = settings
        self.counts: Counter[str] = Counter({topic: 0 for topic in KAFKA_TOPICS})
        self._redis = redis.from_url(settings.redis_url)
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._consumer is not None:
            await self._consumer.stop()
        if self._producer is not None:
            await self._producer.stop()
        await self._redis.aclose()

    async def _run(self) -> None:
        while True:
            try:
                await self._consume()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("kafka consumer unavailable")
                await asyncio.sleep(1)

    async def _consume(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
        servers = self._settings.kafka_bootstrap_servers
        self._producer = AIOKafkaProducer(bootstrap_servers=servers, linger_ms=0)
        self._consumer = AIOKafkaConsumer(
            *KAFKA_TOPICS,
            bootstrap_servers=servers,
            group_id=GROUP_ID,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._producer.start()
        await self._consumer.start()
        async for message in self._consumer:
            cid = correlation_from_headers(message.headers)
            token = correlation_id_var.set(cid) if cid else None
            try:
                with span("worker.consume"):
                    await self._handle(message.topic, message.value or b"")
                await self._consumer.commit()
            finally:
                if token is not None:
                    correlation_id_var.reset(token)

    async def _handle(self, topic: str, raw: bytes) -> None:
        event: ChatEvent | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                event = ChatEvent.model_validate_json(raw)
                break
            except Exception:
                logger.warning("kafka event rejected attempt=%s", attempt)
        if event is None:
            await self._dead_letter(topic, raw)
            return
        if not await self._claim(event.event_id):
            return
        key = f"kafka:event:{event.event_id}"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                self.counts[event.topic] += 1
                logger.info(
                    "kafka event counted topic=%s event_id=%s",
                    event.topic,
                    event.event_id,
                )
                await self._redis.set(key, "done", ex=self._settings.kafka_event_done_seconds)
                return
            except Exception:
                logger.warning(
                    "kafka consume failed topic=%s attempt=%s",
                    event.topic,
                    attempt,
                )
                self.counts[event.topic] = max(0, self.counts[event.topic] - 1)
        await self._redis.delete(key)
        await self._dead_letter(event.topic, raw)

    async def _claim(self, event_id: str) -> bool:
        key = f"kafka:event:{event_id}"
        lock_seconds = self._settings.kafka_event_lock_seconds
        for _ in range(lock_seconds):
            acquired = await self._redis.set(key, "processing", nx=True, ex=lock_seconds)
            if acquired:
                return True
            state = await self._redis.get(key)
            if state == b"done":
                return False
            await asyncio.sleep(1)
        return False

    async def _dead_letter(self, topic: str, raw: bytes) -> None:
        if self._producer is None:
            return
        await self._producer.send_and_wait(kafka_dlq_topic(topic), raw)


def correlation_from_headers(headers) -> str | None:
    if not headers:
        return None
    for key, value in headers:
        if key == "X-Correlation-ID" and value:
            text = value.decode("utf-8", errors="replace")[:128]
            return text or None
    return None


def authorized(header: str, token: str) -> bool:
    try:
        return secrets.compare_digest(header, token)
    except ValueError:
        return False
