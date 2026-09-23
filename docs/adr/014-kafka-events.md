# ADR-014: Metadata-only Kafka events

- Status: Accepted
- Date: 2026-09-23
- Version: 8

## Context

Chat, retrieval, and citation checks already decide an HTTP status inside the gateway. Operators still need a count of requests, responses, and security decisions without a metrics stack. A broker outage must not turn a successful chat into an error. ADR-003 already chose Kafka over RabbitMQ.

## Decision

1. One `apache/kafka` container runs in KRaft mode. There is no ZooKeeper. Each topic has 1 partition and replication factor 1.
2. The gateway and the worker use `aiokafka`. Topics `ai.requests`, `ai.responses`, `ai.security`, and `ai.evaluations` are created from the gateway lifespan, each with a `.dlq` topic. The gateway does not publish evaluation events. The worker still subscribes to `ai.evaluations` and only counts.
3. `ChatEvent` carries `event_id`, `correlation_id`, `tenant_id`, `user_id`, `topic`, `status_code`, `latency_ms`, `rule_ids`, `citation_count`, and `groundedness`. It has no prompt, answer, chunk text, document body, or secret span.
4. After auth, the gateway publishes one request event. When the HTTP result is decided, it publishes one response event. It publishes a security event when the attempt includes an input block, an output block, a `citation_unverified` redact, or an output secret redaction.
5. Produce uses `KAFKA_PUBLISH_TIMEOUT_SECONDS` (default 0.5). On timeout or error the gateway logs the topic and leaves the HTTP status unchanged.
6. The worker uses consumer group `aigateway-analytics`. It retries a message 3 times, then produces to that topic's dead-letter queue and commits the offset. Redis key `kafka:event:{event_id}` is set when processing starts and kept after success so a redelivery is not counted twice. A crash before success lets the TTL expire so a retry can run.
7. `/v1/ready` requires the broker. Chat publish stays best-effort after that. Counts are `GET /internal/v1/counts` on the worker with `X-Internal-Token`, plus a JSON log line. That route is not on the gateway.

## Consequences

- Killing the worker does not change the chat HTTP response.
- A down broker fails readiness and drops events, and chat still returns its existing status.
- Evaluation scores and a public metrics endpoint stay out of this version.

## Alternatives rejected

- **Fail the chat when publish fails:** the client would see a broker problem as a model failure.
- **Put the prompt in the event:** logs and the bus would hold user text and secrets.
- **ZooKeeper or a second broker:** one KRaft node is enough for this slice.
- **Publish evaluation events now:** the topic exists so the worker can count them later. Scoring stays a later version.
