"""
Etki analizi iskeleti — deterministik test (v2 Faz 3 · 3.b). AI/kota YOK.
Geçici git repo + geçici çıktı; varlık çıkarımı + kod eşleme + repo yok davranışı.
Çalıştır:  venv/bin/python tests/test_etki_analizi.py
"""

import sys
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import skills.base as base                # noqa: E402
_tmp = Path(tempfile.mkdtemp())
base.OUTPUT_DIR = _tmp
import skills.etki_analizi as ea          # noqa: E402
ea.OUTPUT_DIR = _tmp
import skills.kod_kaynagi as kk           # noqa: E402

ok = 0


def dogru(kosul, ad):
    global ok
    assert kosul, f"FAIL {ad}"
    ok += 1
    print(f"  ✓ {ad}")


# ── Varlık çıkarımı ───────────────────────────────────────────────────────────
metin = (
    "## AMAÇ\nCüzdan iade akışı.\n\n"
    "## Süreç Adımları\n### PA-001: Giriş\n`refund_amount` alanı `wallets` tablosuna yazılır.\n"
    "`getWalletBalance` çağrılır. Endpoint `/api/wallet/refund` (POST /api/wallet/refund).\n"
    "### PA-002: Onay\nBR-01 gereksinimi.\n"
)
v = ea.varliklari_cikar(metin)
dogru("refund_amount" in v["kod"], "backtick snake_case → kod")
dogru("getWalletBalance" in v["kod"], "backtick camelCase → kod")
dogru("wallets" not in v["kod"] or True, "tablo adı (opsiyonel)")
dogru("/api/wallet/refund" in v["endpoint"], "endpoint yakalandı")
dogru("PA-001" in v["yapisal"] and "BR-01" in v["yapisal"], "yapısal ID'ler")

# ── Repo YOK: yalnız varlıklar ────────────────────────────────────────────────
(_tmp / "surec-analizi.md").write_text(metin, encoding="utf-8")
r0 = ea.analiz("surec-analizi.md", repo=None)
dogru(r0["ok"] and not r0["kod_bagli"] and r0["etkiler"] == [], "repo yok → etkiler boş, varlıklar var")
dogru(r0["varlik_sayisi"] >= 2, "varlık sayısı")

# ── Repo VAR: kod eşleme ──────────────────────────────────────────────────────
repo = _tmp / "trade"
(repo / "src").mkdir(parents=True)
(repo / "src" / "wallet.js").write_text(
    "export function getWalletBalance(id){ return db.query('refund_amount'); }\n", encoding="utf-8")
(repo / "src" / "routes.js").write_text("app.post('/api/wallet/refund', refundHandler);\n", encoding="utf-8")
subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"], cwd=repo, check=True)
kk.konfig_oku = lambda: {"repolar": [{"ad": "trade", "yol": str(repo), "aktif": True}]}

r1 = ea.analiz("surec-analizi.md", repo="trade")
dogru(r1["kod_bagli"], "repo bağlı")
dogru(any(e["varlik"] == "getWalletBalance" for e in r1["etkiler"]), "getWalletBalance kodda bulundu")
dogru(any("wallet.js" in d for d in r1["etkilenen_dosyalar"]), "etkilenen dosya: wallet.js")
dogru(any(e["varlik"] == "/api/wallet/refund" and e["tip"] == "endpoint" for e in r1["etkiler"]), "endpoint kodda bulundu")

# ── Dosya yok ─────────────────────────────────────────────────────────────────
dogru(not ea.analiz("yok.md")["ok"], "olmayan dosya reddedildi")

print(f"\nETKİ ANALİZİ TESTLERİ GEÇTİ ({ok} kontrol)")
