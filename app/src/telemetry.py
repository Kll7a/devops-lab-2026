"""Единая точка настройки телеметрии.

Трассировку и базовые метрики включает opentelemetry-instrument (авто-инструментация)
через переменные окружения. Здесь мы создаём только СВОИ бизнес-метрики,
которых автоматика знать не может.
"""
from opentelemetry import metrics

meter = metrics.get_meter("demo-api")

orders_created = meter.create_counter(
    "orders_created",
    unit="1",
    description="Сколько заказов создано",
)
orders_processed = meter.create_counter(
    "orders_processed",
    unit="1",
    description="Сколько заказов обработал worker",
)
cache_lookups = meter.create_counter(
    "orders_cache_lookups",
    unit="1",
    description="Обращения к кэшу заказов (атрибут result=hit|miss)",
)
