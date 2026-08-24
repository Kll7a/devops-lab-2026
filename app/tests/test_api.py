import src.main as m


def test_openapi_schema_is_valid():
    """Проверяем, что схема генерируется и содержит наши эндпоинты."""
    schema = m.app.openapi()
    assert "/orders" in schema["paths"]
    assert schema["info"]["version"] == "1.0.0"


def test_order_model_rejects_bad_qty():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        m.OrderIn(item="book", qty=0)
