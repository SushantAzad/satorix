"""
Streaming worker entry point.

Reads KAFKA_TOPICS env var (comma-separated list of "topic:client_id:source_id" triples),
starts one StreamingIngestionConsumer per topic, and runs until SIGTERM.

Environment variables:
  KAFKA_BOOTSTRAP_SERVERS  — e.g. "kafka:9092" (default)
  KAFKA_TOPICS             — e.g. "mca21.raw:infracore:source-uuid-1,sebi.raw:infracore:source-uuid-2"
  KAFKA_GROUP_ID           — consumer group (default: "infracore-l1-streaming")
  KAFKA_MAX_BATCH_SIZE     — records per micro-batch (default: 1000)
  KAFKA_MAX_BATCH_SECONDS  — time window per micro-batch (default: 60)
  REDIS_URL                — Redis connection string

Run:
  python -m layer1_ingestion.streaming.streaming_worker
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_topics(raw: str) -> list[tuple[str, str, str]]:
    """Parse 'topic:client_id:source_id,...' into a list of triples."""
    result = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 3:
            logger.warning("Skipping malformed KAFKA_TOPICS entry (need topic:client_id:source_id): %s", entry)
            continue
        topic = parts[0]
        client_id = parts[1]
        source_id = ":".join(parts[2:])  # source_id may contain colons if it's a UUID
        result.append((topic, client_id, source_id))
    return result


def main() -> None:
    if os.environ.get("LOCAL_SAFE_MODE", "true").lower() != "false":
        logger.warning("LOCAL SAFE MODE: streaming ingestion disabled")
        return
    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    topics_raw = os.environ.get("KAFKA_TOPICS", "")
    group_id = os.environ.get("KAFKA_GROUP_ID", "infracore-l1-streaming")
    max_batch_size = int(os.environ.get("KAFKA_MAX_BATCH_SIZE", "1000"))
    max_batch_seconds = float(os.environ.get("KAFKA_MAX_BATCH_SECONDS", "60"))
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

    if not topics_raw:
        logger.warning(
            "KAFKA_TOPICS not set — streaming worker idle. "
            "Set KAFKA_TOPICS=topic:client_id:source_id to activate."
        )
        # Stay alive so the container doesn't restart-loop
        while True:
            time.sleep(60)

    topic_list = _parse_topics(topics_raw)
    if not topic_list:
        logger.error("No valid topics parsed from KAFKA_TOPICS=%r — exiting", topics_raw)
        sys.exit(1)

    from layer1_ingestion.core.database import SessionLocal
    from layer1_ingestion.streaming.kafka_consumer import StreamingIngestionConsumer
    from layer1_ingestion.streaming.stream_processor import StreamProcessor

    consumers: list[StreamingIngestionConsumer] = []

    for topic, client_id, source_id in topic_list:
        processor = StreamProcessor(
            client_id=client_id,
            source_id=source_id,
            db_session_factory=SessionLocal,
            redis_url=redis_url,
        )
        consumer = StreamingIngestionConsumer(
            topic=topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            on_batch=processor.process,
            max_batch_size=max_batch_size,
            max_batch_seconds=max_batch_seconds,
        )
        consumers.append(consumer)
        consumer.start()
        logger.info("Started consumer: topic=%s client=%s source=%s", topic, client_id, source_id)

    def _shutdown(signum, frame):
        logger.info("SIGTERM received — shutting down streaming worker")
        for c in consumers:
            c.stop(timeout=15)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info(
        "Streaming worker running: %d topic(s), group=%s, batch=%d records / %gs",
        len(consumers), group_id, max_batch_size, max_batch_seconds,
    )

    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
