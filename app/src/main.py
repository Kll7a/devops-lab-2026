import json
import os
import uuid
from contextlib import asynccontextmanager

import aio_pika
import asyncpg
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .telemetry import cache_lookups, orders_created

# Читаем переменные окружения на уровне модуля через os.getenv (не os.environ[...]!).
# Это НЕ падает, если переменной нет — значение будет None.
# Важно: импорт этого модуля (тестами, линтерами, скриптом проверки OpenAPI-схемы)
# не должен требовать наличия боевых подключений к БД/очереди.
PG_URI = os.getenv("PG_URI")
REDIS_URL = os.getenv("REDIS_URL", "redis://valkey:6379/0")
AMQP_URL = os.getenv("AMQP_URL")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "60"))
QUEUE = "orders"

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id         uuid PRIMARY KEY,
    item       text        NOT NULL,
    qty        integer     NOT NULL CHECK (qty > 0),
    status     text        NOT NULL DEFAULT 'NEW',
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


class OrderIn(BaseModel):
    item: str = Field(min_length=1, max_length=64, examples=["book"])
    qty: int = Field(gt=0, le=100, examples=[2])


class Order(BaseModel):
    id: uuid.UUID
    item: str
    qty: int
    status: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # А вот здесь приложение РЕАЛЬНО стартует и обязано подключаться к внешним
    # сервисам — поэтому именно тут, а не при импорте, мы проверяем обязательность
    # переменных и явно объясняем, чего не хватает.
    if not PG_URI:
        raise RuntimeError(
            "Переменная окружения PG_URI обязательна для запуска приложения "
            "(например: postgresql://demo:demo@localhost:5432/demo)"
        )
    if not AMQP_URL:
        raise RuntimeError(
            "Переменная окружения AMQP_URL обязательна для запуска приложения "
            "(например: amqp://demo:demo@localhost:5672/)"
        )

    # Соединения открываем один раз при старте, а не на каждый запрос.
    app.state.pg = await asyncpg.create_pool(PG_URI, min_size=1, max_size=8)
    async with app.state.pg.acquire() as conn:
        await conn.execute(SCHEMA)

    app.state.redis = redis.from_url(REDIS_URL, decode_responses=True)

    app.state.amqp = await aio_pika.connect_robust(AMQP_URL)
    channel = await app.state.amqp.channel()
    await channel.declare_queue(QUEUE, durable=True)
    app.state.channel = channel

    yield  # <-- здесь приложение работает и обслуживает запросы

    await app.state.amqp.close()
    await app.state.redis.aclose()
    await app.state.pg.close()


app = FastAPI(
    title="Orders API",
    version="1.0.0",
    description="Демо-сервис лаборатории DevOps Lab 2026: PostgreSQL + Valkey + RabbitMQ.",
    lifespan=lifespan,
)


@app.get("/healthz", tags=["ops"], summary="Живость процесса")
async def healthz():
    # Liveness: НЕ ходит в БД/очередь. Если тут будет ошибка — Kubernetes
    # начнёт бесконечно перезапускать здоровый процесс из-за чужой проблемы.
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"], summary="Готовность к трафику")
async def readyz():
    # Readiness: наоборот, обязан проверять реальные зависимости — если БД
    # недоступна, под должны временно убрать из балансировки.
    try:
        async with app.state.pg.acquire() as conn:
            await conn.fetchval("SELECT 1")
        await app.state.redis.ping()
        if app.state.amqp.is_closed:
            raise RuntimeError("amqp closed")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"not ready: {exc}") from exc
    return {"status": "ready"}


@app.post("/orders", response_model=Order, status_code=201, tags=["orders"])
async def create_order(payload: OrderIn):
    order_id = uuid.uuid4()
    async with app.state.pg.acquire() as conn:
        await conn.execute(
            "INSERT INTO orders (id, item, qty) VALUES ($1, $2, $3)",
            order_id, payload.item, payload.qty,
        )

    await app.state.channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps({"id": str(order_id)}).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=QUEUE,
    )

    orders_created.add(1, {"item": payload.item})
    return Order(id=order_id, item=payload.item, qty=payload.qty, status="NEW")


@app.get("/orders/{order_id}", response_model=Order, tags=["orders"])
async def get_order(order_id: uuid.UUID):
    key = f"order:{order_id}"

    cached = await app.state.redis.get(key)
    if cached:
        cache_lookups.add(1, {"result": "hit"})
        return Order(**json.loads(cached))

    cache_lookups.add(1, {"result": "miss"})
    async with app.state.pg.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, item, qty, status FROM orders WHERE id = $1", order_id
        )
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")

    order = Order(id=row["id"], item=row["item"], qty=row["qty"], status=row["status"])
    await app.state.redis.set(key, order.model_dump_json(), ex=CACHE_TTL)
    return order
