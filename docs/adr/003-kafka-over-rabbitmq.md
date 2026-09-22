# ADR-003: Kafka over RabbitMQ

- Status: Accepted (not running in Version 1)
- Date: 2026-09-21
- Version: 1

## Context

Production traffic should publish `ai.requests`, `ai.responses`, `ai.security`, and `ai.evaluations` for workers and analytics. Version 1 does not start a broker so local startup stays small.

## Decision

**Kafka** is the event bus when Version 8 lands. RabbitMQ is not the backbone. This ADR records the decision now so services do not grow ad-hoc queues.

## Consequences

- Version 1 compose file has no Kafka (and no ZooKeeper/KRaft).
- Event payload schemas will live in `packages/contracts` before a broker is added.
- Replay and consumer groups fit audit/eval consumers better than competing consumers on AMQP work queues.

## Alternatives rejected

- **RabbitMQ**: excellent for task queues; weaker fit for durable, replayable domain event logs.
- **HTTP-only workers**: couples latency of evals/analytics to the user request.
