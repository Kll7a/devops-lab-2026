"""Фоновый обработчик: читает очередь, обновляет статус, чистит кэш."""
import asyncio
import json
import os

import aio_pika
import asyncpg
import redis.asyncio as redis

from .telemetry import orders_processed

# Как и в main.py: os.getenv (не os.environ[...]) — импорт модуля не должен
# требовать боевых подключений. Обязательность проверяем только внутри main(),
# то есть в момент реального запуска воркера.
PG_URI = os.getenv("PG_URI")
REDIS_URL = os.getenv("REDIS_URL", "redis://valkey:6379/0")
AMQP_URL = os.getenv("AMQP_URL")
QUEUE = "orders"
WORK_SECONDS = float(os.getenv("WORK_SECONDS", "0.4"))


async def main() -> None:
    if not PG_URI:
        raise RuntimeError(
            "Переменная окружения PG_URI обязательна для запуска воркера "
            "(например: postgresql://demo:demo@localhost:5432/demo)"
        )
    if not AMQP_URL:
        raise RuntimeError(
            "Переменная окружения AMQP_URL обязательна для запуска воркера "
            "(например: amqp://demo:demo@localhost:5672/)"
        )

    pool = await asyncpg.create_pool(PG_URI, min_size=1, max_size=4)
    cache = redis.from_url(REDIS_URL, decode_responses=True)
    connection = await aio_pika.connect_robust(AMQP_URL)

    channel = await connection.channel()
    # prefetch=8: не забираем из очереди больше, чем реально успеваем обработать
    await channel.set_qos(prefetch_count=8)
    queue = await channel.declare_queue(QUEUE, durable=True)

    print("worker: жду сообщения", flush=True)
    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():          # ack только после успешной обработки
                order_id = json.loads(message.body)["id"]
                await asyncio.sleep(WORK_SECONDS)  # имитация полезной работы
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE orders SET status = 'DONE' WHERE id = $1::uuid", order_id
                    )
                await cache.delete(f"order:{order_id}")
                orders_processed.add(1)


if __name__ == "__main__":
    asyncio.run(main())
