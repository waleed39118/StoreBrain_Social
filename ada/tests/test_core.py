import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor

from app.core.assistant import parse_intent


def test_auth_required(client):
    assert client.get("/api/v1/products", headers={"X-API-Key": "bad"}).status_code == 401


def test_sale_decrements_and_alerts(seeded):
    r = seeded.post("/api/v1/sales", json={"items": [{"sku": "MILK-1L", "quantity": 3}]})
    assert r.status_code == 201 and r.json()["total"] == "4.50"
    low = seeded.get("/api/v1/inventory/low-stock").json()
    assert [p["sku"] for p in low] == ["MILK-1L"] and low[0]["stock_qty"] == 9


def test_oversell_rejected_atomically(seeded):
    r = seeded.post("/api/v1/sales", json={"items": [{"sku": "EGG-12", "quantity": 1},
                                                     {"sku": "MILK-1L", "quantity": 99}]})
    assert r.status_code == 422
    eggs = seeded.get("/api/v1/products", params={"q": "EGG-12"}).json()[0]
    assert eggs["stock_qty"] == 30  # first line rolled back


def test_concurrent_sales_never_oversell(seeded):
    def buy():
        return seeded.post("/api/v1/sales", json={"items": [{"sku": "MILK-1L", "quantity": 1}]}).status_code
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda _: buy(), range(20)))
    assert codes.count(201) == 12
    assert seeded.get("/api/v1/products", params={"q": "MILK-1L"}).json()[0]["stock_qty"] == 0


def test_intent_parsing_bilingual():
    assert vars(parse_intent("sell 2 milk")) == {"name": "sell", "product_query": "milk", "quantity": 2}
    i = parse_intent("بيع ٣ حليب")
    assert (i.name, i.product_query, i.quantity) == ("sell", "حليب", 3)
    assert parse_intent("كم باقي من بيض؟").name == "stock"
    assert parse_intent("what should I reorder").name == "reorder"


def test_chat_flows(seeded):
    r = seeded.post("/api/v1/ada/chat", json={"text": "بيع 2 حليب"}).json()
    assert r["intent"] == "sell" and r["language"] == "ar" and "10" in r["reply"]
    r = seeded.post("/api/v1/ada/chat", json={"text": "how many eggs"}).json()
    assert "30" in r["reply"]
    r = seeded.post("/api/v1/ada/chat", json={"text": "best sellers"}).json()
    assert r["data"][0]["sku"] == "MILK-1L"


def test_analytics(seeded):
    seeded.post("/api/v1/sales", json={"items": [{"sku": "MILK-1L", "quantity": 4}]})
    reorder = {r["sku"]: r for r in seeded.get("/api/v1/analytics/reorder").json()}
    assert "MILK-1L" in reorder and reorder["MILK-1L"]["order_qty"] > 0
    assert "SOAP" not in reorder  # damaged -> obsolete, never reordered
    assert any(r["sku"] == "SOAP" for r in seeded.get("/api/v1/analytics/obsolete").json())
    d = seeded.get("/api/v1/analytics/diversification").json()
    assert d["concentration"] == "high" and d["categories"][0]["category"] == "dairy"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()


def test_patch_signed_idempotent(seeded):
    body = json.dumps({"version": "v1", "products": [
        {"sku": "MILK-1L", "price": 1.75, "stock_delta": 24},
        {"sku": "BREAD", "name_en": "Bread", "name_ar": "خبز", "price": 0.9, "category": "bakery"}]}).encode()
    assert seeded.post("/api/v1/system/patches", content=body,
                       headers={"X-Ada-Signature": "sha256=bad"}).status_code == 400
    r = seeded.post("/api/v1/system/patches", content=body, headers={"X-Ada-Signature": _sign(body)})
    assert r.json() == {"version": "v1", "applied": True, "created": 1, "updated": 1}
    r = seeded.post("/api/v1/system/patches", content=body, headers={"X-Ada-Signature": _sign(body)})
    assert r.json()["applied"] is False
    milk = seeded.get("/api/v1/products", params={"q": "MILK-1L"}).json()[0]
    assert milk["stock_qty"] == 36 and milk["price"] == "1.75"


def test_bad_patch_rolls_back(seeded):
    body = json.dumps({"version": "v2", "products": [
        {"sku": "EGG-12", "price": 9}, {"sku": "NEW", "price": 1}]}).encode()  # NEW lacks name_en
    assert seeded.post("/api/v1/system/patches", content=body,
                       headers={"X-Ada-Signature": _sign(body)}).status_code == 400
    assert seeded.get("/api/v1/products", params={"q": "EGG-12"}).json()[0]["price"] == "3.00"


def test_voice_endpoint_with_stub(seeded, monkeypatch):
    from app.core.voice_engine import Transcript
    from app.main import app
    monkeypatch.setattr(app.state.voice, "transcribe", lambda a, s: Transcript("how many eggs", "en"))
    r = seeded.post("/api/v1/ada/voice", files={"audio": ("a.wav", b"RIFF....", "audio/wav")},
                    data={"speak": "false"})
    assert r.status_code == 200 and r.json()["transcript"] == "how many eggs" and "30" in r.json()["reply"]


def test_audio_path_traversal_blocked(client):
    assert client.get("/api/v1/audio/..%2F..%2Fetc%2Fpasswd").status_code == 404
