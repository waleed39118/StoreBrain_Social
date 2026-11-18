import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["ADA_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADA_TTS_OUTPUT_DIR"] = f"{_tmp}/tts"
os.environ["ADA_API_KEY"] = "test-key"
os.environ["ADA_UPDATER_HMAC_SECRET"] = "s3cret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app, headers={"X-API-Key": "test-key"}) as c:
        yield c


@pytest.fixture()
def seeded(client):
    for p in [
        {"sku": "MILK-1L", "name_en": "Milk", "name_ar": "حليب", "category": "dairy",
         "price": "1.50", "cost": "1.00", "stock_qty": 12, "reorder_level": 10},
        {"sku": "EGG-12", "name_en": "Eggs", "name_ar": "بيض", "category": "dairy",
         "price": "3.00", "stock_qty": 30, "reorder_level": 5},
        {"sku": "SOAP", "name_en": "Soap", "category": "care", "price": "2.00",
         "stock_qty": 50, "reorder_level": 5, "condition": "damaged"},
    ]:
        assert client.post("/api/v1/products", json=p).status_code == 201
    return client
