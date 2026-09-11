"""
Hafif regresyon güvencesi — v2 Faz 2.6.

Flask test client ile DETERMİNİSTİK uçları dener (AI çağrısı YOK, kota YOK, ağ YOK).
Çalıştır:  venv/bin/python tests/smoke_test.py
Kural: her yeni deterministik endpoint buraya bir satır ekler. Gerçek output/'a
dokunmaz (geçici OUTPUT_DIR); 5002/5003 süreçlerinden bağımsız çalışır.
"""

import importlib
import inspect
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("AUTO_UPDATE", "false")      # arka plan thread'i başlatma
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("JIRA_KOPRU", "false")       # köprü döngüsünü başlatma + durum testi deterministik
os.environ.setdefault("JIRA_KOPRU_PROJELER", "")   # makinenin .env'i (JIRA_KOPRU=true) test sonucunu etkilemesin

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
kontrol("ray görünümü kapları + klasik paneller korunmuş",
        'id="surec-ray"' in govde and 'id="brd-ray"' in govde and govde.count('gorunum-klasik') >= 4
        and 'id="surec-act-teknik-onay"' in govde and 'id="btn-sadece-teknik"' in govde)
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

# ── Faz 3: rol-duyarlı pano + disk temizlik ──
pn = json_al(istemci.get("/api/pano"))
kontrol("pano ok + alanlar", pn.get("ok") and all(k in pn for k in ("workflow", "onay", "sorular", "bekleyen_revizyon", "rol")))
dd = json_al(istemci.get("/api/disk/durum"))
kontrol("disk/durum ok (plan kuru)", dd.get("ok") and "adaylar" in dd.get("plan", {}) and "bos_gb" in dd.get("dosya_sistemi", {}))
_dt = importlib.import_module("skills.disk_temizlik")
kontrol("disk_temizlik: output/ ve input/ kurallarda YOK",
        not any(str(d).endswith(("/output", "/input")) for d, *_ in _dt._KURALLAR))
kontrol("saglik disk_temizlik alanı", "disk_temizlik" in json_al(istemci.get("/api/saglik")))

# ── Jira Köprüsü (polling + taslak/onay) — deterministik uçlar (Jira'sız) ──
jk = json_al(istemci.get("/api/jira-kopru/durum"))
kontrol("jira-kopru/durum ok + varsayılan KAPALI",
        jk.get("ok") and jk.get("ayarlar", {}).get("aktif") is False and jk["ayarlar"].get("komut") == "/analyst_agent")
jkt = istemci.post("/api/jira-kopru/tara", headers=ORIGIN)
kontrol("jira-kopru/tara projesiz → ok:False (Jira'ya gitmeden)",
        json_al(jkt).get("ok") is False and "PROJELER" in json_al(jkt).get("error", ""))
_jkm = importlib.import_module("skills.jira_kopru")
kontrol("jira_kopru: kendi 🤖 yanıtı komut sayılmaz (döngü koruması)",
        _jkm._komut_coz(_jkm.ROBOT_IMZA + " — Teknik Analiz", "/analyst_agent") is None)

# ── Oturum 'aktif' bayrağı + Ayarlar CLI hesap alanı + soru mezar-taşı ──
ot = json_al(istemci.get("/api/oturum"))
kontrol("oturum aktif alanı var (idle → False)", "aktif" in ot and ot.get("aktif") is False)
kontrol("settings cli_hesap alanı var", "cli_hesap" in json_al(istemci.get("/api/settings")))
cf = json_al(istemci.get("/api/context-filter"))
kontrol("context-filter parola maskeli (browser'a sızmıyor)",
        "password" not in cf.get("live_app_auth", {}) and "has_password" in cf.get("live_app_auth", {}))
_sm = importlib.import_module("skills.sorular")
kontrol("sorular: tombstone fonksiyonları", hasattr(_sm, "tumunu_sil") and hasattr(_sm, "_tombstone_ekle"))

# ── Faz 4: analist-dostu hata mesajları (deterministik sınıflandırma) ──
_ht = importlib.import_module("skills.hatalar")
kontrol("hatalar: 429 → cli_limit", _ht.insanlastir("Claude kullanım limitine ulaşıldı: resets 3pm")["kategori"] == "cli_limit")
kontrol("hatalar: OAuth → cli_oturum", _ht.insanlastir("RuntimeError: OAuth token expired\nTraceback (most recent call last):\n x")["kategori"] == "cli_oturum")
kontrol("hatalar: zaman aşımı", _ht.insanlastir("Zaman aşımı (20 dakika). Alt süreç sonlandırıldı.")["kategori"] == "zaman_asimi")
_bil = _ht.insanlastir("Süreç analizi hatası: XyzError boom\nTraceback (most recent call last):\n  File ...")
kontrol("hatalar: bilinmeyen → ilk satır başlık, traceback atıldı", _bil["kategori"] == "bilinmeyen" and _bil["baslik"].startswith("Süreç analizi hatası") and "Traceback" not in _bil["baslik"])
kontrol("hatalar: None → None", _ht.insanlastir(None) is None)
kontrol("workflow-state hata_ozet alanı", "hata_ozet" in json_al(istemci.get("/api/workflow-state")))

# Yetki paneli: bayrak kapalıyken (analist kurulumu) 403 + nav gizli; bayrak açılınca katalog gelir.
# (Owner makinesinde .env USAGE_DASHBOARD=true olabilir → açıkça kapat.)
os.environ["YETKI_PANELI"] = "false"
kontrol("gorunurluk bayrak kapalı → 403 (analist kurulumu)", istemci.get("/api/gorunurluk").status_code == 403)
kontrol("auth/me yetki_admin=false", json_al(istemci.get("/api/auth/me")).get("yetki_admin") is False)
os.environ["YETKI_PANELI"] = "true"
# Görev analizi düzelt endpoint'i — girdi doğrulaması (AI/Jira'ya gitmeden 400)
kontrol("gorev/duzelt geçersiz görev → 400",
        istemci.post("/api/jira/gorev/duzelt", json={"markdown": "x", "talimat": "y"}, headers=ORIGIN).status_code == 400)
kontrol("gorev/duzelt eksik talimat → 400",
        istemci.post("/api/jira/gorev/duzelt", json={"gorev": {"key": "X-1"}, "markdown": "x"}, headers=ORIGIN).status_code == 400)
_jg = importlib.import_module("skills.jira_gorevleri")
_sig = inspect.signature(_jg.gorev_analiz_et).parameters
kontrol("jira_gorevleri: gorev_analiz_duzelt + cevaplar param",
        hasattr(_jg, "gorev_analiz_duzelt") and "cevaplar" in _sig)
kontrol("jira_gorevleri: ilişkili FE/BE (gorev_getir + iliskili/katman param)",
        hasattr(_jg, "gorev_getir") and "iliskili" in _sig and "katman" in _sig)
# Arka plan iş modeli — girdi doğrulaması (AI/Jira'ya gitmeden)
kontrol("gorev/is/baslat boş adımlar → 400",
        istemci.post("/api/jira/gorev/is/baslat", json={"adimlar": []}, headers=ORIGIN).status_code == 400)
kontrol("gorev/is/durum bilinmeyen → 404",
        istemci.get("/api/jira/gorev/is/durum?job=yok123").status_code == 404)
kontrol("gorev/is/durdur bilinmeyen → 404",
        istemci.post("/api/jira/gorev/is/durdur", json={"job": "yok123"}, headers=ORIGIN).status_code == 404)

g = json_al(istemci.get("/api/gorunurluk"))
kontrol("gorunurluk katalog (YETKI_PANELI=true)", g.get("ok") and len(g.get("katalog", [])) >= 10)
kontrol("auth/me yetki_admin=true", json_al(istemci.get("/api/auth/me")).get("yetki_admin") is True)

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
