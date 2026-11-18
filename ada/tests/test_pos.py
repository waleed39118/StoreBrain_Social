import time
from datetime import datetime, timedelta, timezone

from tests.conftest import GATEWAY, OWNER


def _cashier(c, phone="0500000010"):
    c.post("/api/v1/users", json={"phone": phone, "name": "Sara", "role": "cashier", "pin": "4821"})
    tok = c.post("/api/v1/auth/pin/login", json={"phone": phone, "pin": "4821"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_pos_sale_receipt_and_tax(seeded):
    r = seeded.post("/api/v1/pos/sales", json={"items": [{"sku": "EGG-12", "quantity": 2}],
                                                "payment_method": "card", "client_ref": "till1-0001"})
    assert r.status_code == 201
    rc = r.json()
    # 6.00 incl. 15% VAT -> tax 0.78, subtotal 5.22
    assert (rc["total"], rc["tax"], rc["subtotal"], rc["payment_method"]) == ("6.00", "0.78", "5.22", "card")
    assert rc["cashier"] == "Owner" and rc["items"][0]["name_ar"] == "بيض"
    again = seeded.post("/api/v1/pos/sales", json={"items": [{"sku": "EGG-12", "quantity": 2}],
                                                    "client_ref": "till1-0001"}).json()
    assert again["id"] == rc["id"]                                       # idempotent
    assert seeded.get("/api/v1/products", params={"q": "EGG-12"}).json()[0]["stock_qty"] == 28


def test_offline_sync_clamps_and_flags(seeded):
    sold = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    body = {"sales": [
        {"client_ref": "off-0000001", "sold_at": sold, "items": [{"sku": "MILK-1L", "quantity": 15}]},
        {"client_ref": "off-0000002", "sold_at": sold, "items": [{"sku": "NOPE", "quantity": 1}]}]}
    res = seeded.post("/api/v1/pos/sync", json=body).json()["results"]
    assert [r["status"] for r in res] == ["ok", "error"]
    assert seeded.post("/api/v1/pos/sync", json=body).json()["results"][0]["sale_id"] == res[0]["sale_id"]
    assert seeded.get("/api/v1/products", params={"q": "MILK-1L"}).json()[0]["stock_qty"] == 0
    kinds = {n["kind"] for n in seeded.get("/api/v1/notifications").json()}
    assert {"stock_discrepancy", "out_of_stock"} <= kinds
    rc = seeded.get(f"/api/v1/sales/{res[0]['sale_id']}").json()
    assert rc["channel"] == "offline" and rc["created_at"].startswith(sold[:13])


def test_cashier_sees_only_own_sales(seeded):
    seeded.post("/api/v1/pos/sales", json={"items": [{"sku": "EGG-12", "quantity": 1}]})
    h = _cashier(seeded)
    mine = seeded.post("/api/v1/pos/sales", headers=h, json={"items": [{"sku": "EGG-12", "quantity": 1}]}).json()
    listed = seeded.get("/api/v1/sales", headers=h).json()
    assert [s["id"] for s in listed] == [mine["id"]]
    assert seeded.get(f"/api/v1/sales/{mine['id'] - 1}", headers=h).status_code == 404
    assert len(seeded.get("/api/v1/sales").json()) == 2
    assert seeded.get("/api/v1/dashboard/summary", headers=h).status_code == 403


def test_dashboard_summary(seeded):
    seeded.post("/api/v1/pos/sales", json={"items": [{"sku": "EGG-12", "quantity": 3},
                                                     {"sku": "MILK-1L", "quantity": 1}]})
    d = seeded.get("/api/v1/dashboard/summary").json()
    assert d["today"]["revenue"] == "10.50" and d["today"]["sales"] == 1 and d["today"]["items"] == 4
    assert d["top_today"][0]["sku"] == "EGG-12" and len(d["last_7_days"]) == 7
    assert d["last_7_days"][-1]["revenue"] == "10.50"


def test_store_profile(seeded):
    prof = seeded.get("/api/v1/store/profile").json()
    assert prof["currency"] == "SAR" and not prof["setup_completed"]
    prof.update(store_name="بقالة النور", setup_completed=True)
    assert seeded.put("/api/v1/store/profile", json=prof).status_code == 200
    assert seeded.put("/api/v1/store/profile", json={**prof, "timezone": "Mars/Base"}).status_code == 422
    assert seeded.put("/api/v1/store/profile", headers=_cashier(seeded), json=prof).status_code == 403
    assert seeded.get("/api/v1/store/profile").json()["store_name"] == "بقالة النور"


def test_catalog_etag(seeded):
    r = seeded.get("/api/v1/pos/catalog")
    assert len(r.json()) == 3
    assert seeded.get("/api/v1/pos/catalog", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    seeded.patch("/api/v1/products/EGG-12", json={"price": "3.25"})
    assert seeded.get("/api/v1/pos/catalog", headers={"If-None-Match": r.headers["etag"]}).status_code == 200


def test_demo_data_and_backups(client):
    assert client.post("/api/v1/setup/demo-data").json() == {"created": 16}
    assert client.post("/api/v1/setup/demo-data").status_code == 409
    name = client.post("/api/v1/system/backups").json()["name"]
    assert [b["name"] for b in client.get("/api/v1/system/backups").json()][0] == name
    dl = client.get(f"/api/v1/system/backups/{name}")
    assert dl.status_code == 200 and dl.content[:15] == b"SQLite format 3"
    assert client.get("/api/v1/system/backups/..%2Fada.db").status_code == 404


def test_gateway_long_poll_status_pairing(client):
    t0 = time.monotonic()
    assert client.post("/api/v1/sms-gateway/claim?wait=2", headers=GATEWAY).json() == []
    assert time.monotonic() - t0 >= 1.9
    st = client.get("/api/v1/system/sms-gateway/status").json()
    assert st["online"] and st["last_24h"]["sent"] == 1          # the login OTP
    assert client.post("/api/v1/system/sms-gateway/test").status_code == 202
    t0 = time.monotonic()
    msgs = client.post("/api/v1/sms-gateway/claim?wait=10", headers=GATEWAY).json()
    assert len(msgs) == 1 and msgs[0]["phone"] == OWNER and time.monotonic() - t0 < 2
    pair = client.get("/api/v1/system/sms-gateway/pairing").json()
    assert pair["url"] == "https://shop.example.com" and '"ada":"sms-gateway"' in pair["qr"]
    assert pair["allow"] == [OWNER] and "token" not in pair       # token only inside the QR


def test_security_headers_and_limits(anon):
    r = anon.get("/health")
    assert r.json()["status"] == "ok"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert anon.post("/api/v1/auth/otp/request", content=b"x",
                     headers={"Content-Length": str(50 * 1024 * 1024)}).status_code == 413
    assert anon.get("/docs").status_code in (404, 405)
