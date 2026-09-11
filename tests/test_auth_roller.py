"""
AUTH AÇIK — Owner/Analist rol ve görünürlük enforcement testi (v2 Faz 2.4).
Gerçek .env/users.json'a DOKUNMAZ: env ve USERS_PATH geçici; kota YOK.
Çalıştır:  venv/bin/python tests/test_auth_roller.py
"""

import os
import sys
import json
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ["AUTH_ENABLED"] = "true"
os.environ["ADMIN_USER"] = "owner.test"
os.environ["AUTO_UPDATE"] = "false"
os.environ.setdefault("SECRET_KEY", "test")

from werkzeug.security import generate_password_hash   # noqa: E402
import app as uygulama                                  # noqa: E402

_tmp = Path(tempfile.mkdtemp())
uygulama.USERS_PATH = _tmp / "users.json"
uygulama.USERS_PATH.write_text(json.dumps({
    "owner.test": generate_password_hash("owner123"),
    "analist.test": generate_password_hash("analist123"),
}), encoding="utf-8")
uygulama.GORUNURLUK_PATH = _tmp / "gorunurluk.json"    # gerçek gorunurluk.json'a dokunma
uygulama.OUTPUT_DIR = _tmp

ORIGIN = {"Origin": "http://localhost"}
ok = 0


def kontrol(ad, kosul, detay=""):
    global ok
    assert kosul, f"FAIL {ad} {detay}"
    ok += 1
    print(f"  ✓ {ad}")


def giris(c, u, p):
    return c.post("/api/auth/login", json={"username": u, "password": p}, headers=ORIGIN)


# ── Girişsiz ─────────────────────────────────────────────────────────────────
c = uygulama.app.test_client()
kontrol("girişsiz / → login'e yönlendirir", c.get("/").status_code in (301, 302))
kontrol("girişsiz /api → 401", c.get("/api/oturum").status_code == 401)
kontrol("yanlış şifre 401", giris(c, "analist.test", "yanlis").status_code == 401)

# ── Owner ────────────────────────────────────────────────────────────────────
owner = uygulama.app.test_client()
kontrol("owner giriş", giris(owner, "owner.test", "owner123").status_code == 200)
me = owner.get("/api/auth/me").get_json()
kontrol("owner rol=owner, gizli=[]", me["rol"] == "owner" and me["gizli"] == [], str(me))
kontrol("owner /api/gorunurluk 200", owner.get("/api/gorunurluk").status_code == 200)
r = owner.post("/api/gorunurluk", json={"gizli": ["delta", "backlog-senkron"]}, headers=ORIGIN)
kontrol("owner gizle: delta + backlog", r.get_json()["gizli"] == ["backlog-senkron", "delta"], str(r.get_json()))
kontrol("owner delta endpoint engellenmez (403 değil)", owner.post("/api/delta-analiz", json={}, headers=ORIGIN).status_code != 403)

# ── Analist ──────────────────────────────────────────────────────────────────
an = uygulama.app.test_client()
kontrol("analist giriş", giris(an, "analist.test", "analist123").status_code == 200)
me = an.get("/api/auth/me").get_json()
kontrol("analist rol=analist, gizli listesi gelir", me["rol"] == "analist" and set(me["gizli"]) == {"delta", "backlog-senkron"}, str(me))
kontrol("analist / 200 (uygulama açılır)", an.get("/").status_code == 200)
kontrol("analist açık ekran: /api/oturum 200", an.get("/api/oturum").status_code == 200)
r = an.post("/api/delta-analiz", json={"cr": "x"}, headers=ORIGIN)
kontrol("analist gizli endpoint /api/delta-analiz → 403", r.status_code == 403 and r.get_json().get("gizli") == "delta", str(r.get_json()))
kontrol("analist gizli endpoint /api/backlog/* → 403", an.get("/api/backlog/durum").status_code == 403)
kontrol("analist yönetim: /api/gorunurluk → 403", an.get("/api/gorunurluk").status_code == 403)
kontrol("analist yönetim: /api/saglik → 403", an.get("/api/saglik").status_code == 403)
kontrol("analist yönetim: /api/users → 403", an.get("/api/users").status_code == 403)
kontrol("analist gizli olmayan: /api/revizyon/x 200", an.get("/api/revizyon/surec-analizi.md").status_code == 200)

# ── Owner gizlemeyi kaldırır → analist tekrar erişir ─────────────────────────
owner.post("/api/gorunurluk", json={"gizli": []}, headers=ORIGIN)
kontrol("gizleme kalkınca analist delta 403 değil", an.post("/api/delta-analiz", json={}, headers=ORIGIN).status_code != 403)

kontrol("çıkış", an.post("/api/auth/logout", headers=ORIGIN).status_code == 200 and an.get("/api/oturum").status_code == 401)

print(f"\nAUTH/ROL TESTLERİ GEÇTİ ({ok} kontrol)")
