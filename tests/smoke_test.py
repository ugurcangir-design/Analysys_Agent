"""
Hafif regresyon güvencesi — v2 Faz 2.6.

Flask test client ile DETERMİNİSTİK uçları dener (AI çağrısı YOK, kota YOK, ağ YOK).
Çalıştır:  venv/bin/python tests/smoke_test.py
Kural: her yeni deterministik endpoint buraya bir satır ekler. Gerçek output/'a
dokunmaz (geçici OUTPUT_DIR); 5002/5003 süreçlerinden bağımsız çalışır.
"""

import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("AUTO_UPDATE", "false")      # arka plan thread'i başlatma
os.environ.setdefault("AUTH_ENABLED", "false")

import skills.base as base                         # noqa: E402
_tmp = Path(tempfile.mkdtemp())
base.OUTPUT_DIR = _tmp                             # revizyon depolaması geçici dizine
import skills.revizyon as revizyon                 # noqa: E402
revizyon.OUTPUT_DIR = _tmp
revizyon.REVIZYON_DIR = _tmp / "revizyon"

import app as uygulama                             # noqa: E402
uygulama.OUTPUT_DIR = _tmp                         # app.py'nin çıktı dizini de geçici (onayla → yazım)

istemci = uygulama.app.test_client()
ORIGIN = {"Origin": "http://localhost"}            # CSRF same-origin
basari = 0


def kontrol(ad: str, kosul: bool, detay: str = "") -> None:
    global basari
    if not kosul:
        raise SystemExit(f"FAIL {ad} {detay}")
    basari += 1
    print(f"  ✓ {ad}")


def json_al(r):
    return r.get_json() or {}


# ── Sayfa ve temel uçlar ──────────────────────────────────────────────────────
r = istemci.get("/")
kontrol("GET / 200", r.status_code == 200)
govde = r.get_data(as_text=True)
for pid in ("page-pano", "page-surec", "page-ciktilar", "page-revizyon", "page-delta", "page-yetki", "og-banner", "pl-overlay"):
    kontrol(f"render {pid}", f'id="{pid}"' in govde)
kontrol("ds.css link", "/static/ds.css" in govde)
kontrol("GET /static/ds.css 200", istemci.get("/static/ds.css").status_code == 200)

me = json_al(istemci.get("/api/auth/me"))
kontrol("auth/me rol=owner (AUTH kapalı)", me.get("rol") == "owner" and me.get("gizli") == [])

o = json_al(istemci.get("/api/oturum"))
kontrol("oturum ok + katalog", o.get("ok") and len(o.get("ciktilar", [])) >= 9)

su = json_al(istemci.get("/api/sorular/uygula/durum"))
kontrol("sorular/uygula-durum ok (idle)", su.get("ok") and su.get("calisiyor") is False)

# ── Adım sohbeti (Faz 2): geri-don yalnız teknik-onay durumunda; adim/duzelt doğrulamaları ──
kontrol("geri-don teknik-onay dışı → 409", istemci.post("/api/geri-don", headers=ORIGIN).status_code == 409)
r = istemci.post("/api/adim/duzelt", json={"dosya": "yok.md", "talimat": "x"}, headers=ORIGIN)
kontrol("adim/duzelt geçersiz dosya → 400", r.status_code == 400)
r = istemci.post("/api/adim/duzelt", json={"dosya": "surec-analizi.md", "talimat": ""}, headers=ORIGIN)
kontrol("adim/duzelt boş talimat → 400", r.status_code == 400)

g = json_al(istemci.get("/api/gorunurluk"))
kontrol("gorunurluk katalog", g.get("ok") and len(g.get("katalog", [])) >= 10)

u = json_al(istemci.get("/api/guncelleme/durum"))
kontrol("guncelleme/durum ok (fetch yok)", u.get("ok") and "yeni_surum" in u)

s = json_al(istemci.get("/api/saglik"))
kontrol("saglik ok + bölümler", s.get("ok") and all(k in s for k in ("surum", "ai", "guncelleme", "workflow", "disk", "auth")))

k = json_al(istemci.get("/api/kod/repolar"))
kontrol("kod/repolar ok (repo yok da olsa)", k.get("ok") and isinstance(k.get("repolar"), list))
kontrol("kod/agac repo yok → ok:false", json_al(istemci.get("/api/kod/agac?repo=yok&yol=")).get("ok") is False)
(_tmp / "surec-analizi.md").write_text("## AMAÇ\n`getWallet` ve `/api/x` kullanılır.\n", encoding="utf-8")
ea = json_al(istemci.get("/api/etki/surec-analizi.md"))
kontrol("etki analizi: repo yok → varlıklar var, etkiler boş", ea.get("ok") and not ea["kod_bagli"] and ea["varlik_sayisi"] >= 1)
for pid in ("page-kod",):
    kontrol(f"render {pid}", f'id="{pid}"' in govde)

# ── Revizyon oturumu (geçici dizin) ───────────────────────────────────────────
(_tmp / "surec-analizi.md").write_text("## A\nsatır\n", encoding="utf-8")
r = istemci.post("/api/revizyon/surec-analizi.md/baslat", headers=ORIGIN)
kontrol("revizyon baslat", json_al(r).get("ok") and json_al(r)["oturum"]["aktif_versiyon"] == "v1")
rev = revizyon.revizyon_oner("surec-analizi.md", "## A\nsatır DEĞİŞTİ\n", tip="bolum", istek="t", ozet="o")
r = istemci.get("/api/revizyon/surec-analizi.md/diff?a=v1&b=v2")
kontrol("revizyon diff", "DEĞİŞTİ" in json_al(r).get("diff", ""))
r = istemci.post("/api/revizyon/surec-analizi.md/onayla", json={"revizyon_id": rev["id"]}, headers=ORIGIN)
kontrol("revizyon onayla → çıktı yazıldı", json_al(r).get("ok") and "DEĞİŞTİ" in (_tmp / "surec-analizi.md").read_text(encoding="utf-8"))
r = istemci.post("/api/revizyon/surec-analizi.md/geri-al", json={"versiyon_id": "v1"}, headers=ORIGIN)
kontrol("revizyon geri-al", json_al(r).get("ok") and "DEĞİŞTİ" not in (_tmp / "surec-analizi.md").read_text(encoding="utf-8"))

# ── Güvenlik kapıları ─────────────────────────────────────────────────────────
kontrol("CSRF: Origin'siz POST 403", istemci.post("/api/revizyon/surec-analizi.md/baslat").status_code == 403)
kontrol("allowlist: geçersiz dosya 400", istemci.get("/api/revizyon/../etc").status_code in (400, 404))
kontrol("gorunurluk POST geçersiz gövde 400", istemci.post("/api/gorunurluk", json={"gizli": "x"}, headers=ORIGIN).status_code == 400)

print(f"\nSMOKE TESTLERİ GEÇTİ ({basari} kontrol)")
