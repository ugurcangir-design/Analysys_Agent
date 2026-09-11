"""
Revizyon belkemiği + bölüm-hedefli düzenleme deterministik testleri (AI enjekte, kota YOK).
Çalıştır:  venv/bin/python tests/test_revizyon.py
"""

import sys
import importlib
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

tmp = Path(tempfile.mkdtemp())
import skills.base as base                         # noqa: E402
base.OUTPUT_DIR = tmp
import skills.revizyon as r                        # noqa: E402
importlib.reload(r)
r.OUTPUT_DIR = tmp
r.REVIZYON_DIR = tmp / "revizyon"
import skills.revizyon_ai as ra                    # noqa: E402
importlib.reload(ra)
ra.OUTPUT_DIR = tmp
ra.revizyon = r

ok = 0


def esit(a, b, ad):
    global ok
    assert a == b, f"FAIL {ad}: {a!r} != {b!r}"
    ok += 1
    print(f"  ✓ {ad}")


def dogru(kosul, ad):
    global ok
    assert kosul, f"FAIL {ad}"
    ok += 1
    print(f"  ✓ {ad}")


H = "surec-analizi.md"
o = r.baslat(H, "# Rapor\nSatır A\nSatır B\n", "İlk üretim")
esit(o["aktif_versiyon"], "v1", "baslat v1")
esit(r.baslat(H, "FARKLI")["versiyonlar"][0]["hash"], o["versiyonlar"][0]["hash"], "baslat idempotent")

rev = r.revizyon_oner(H, "# Rapor\nSatır A DÜZELTİLDİ\nSatır B\n", tip="bolum", istek="a", ozet="o")
esit(rev["onay_durumu"], "beklemede", "öneri beklemede")
esit(r.oturum_yukle(H)["aktif_versiyon"], "v1", "öneri aktifi değiştirmez")
dogru("DÜZELTİLDİ" in r.diff(H, "v1", "v2"), "diff")

r.onayla(H, rev["id"])
esit(r.oturum_yukle(H)["aktif_versiyon"], "v2", "onay → v2")
try:
    r.onayla(H, rev["id"])
    raise SystemExit("çift onay geçmemeliydi")
except ValueError:
    dogru(True, "çift onay engellendi")

rev2 = r.revizyon_oner(H, "X\n", tip="sohbet")
r.reddet(H, rev2["id"])
esit(r.oturum_yukle(H)["aktif_versiyon"], "v2", "ret aktifi korur")

r.geri_al(H, "v1")
dogru("DÜZELTİLDİ" not in r.onayli_icerik(H), "geri-al")
esit(r.ozet(H)["bekleyen"], None, "bekleyen yok")

MD = ("<!-- m -->\n\n## Amaç\nx\n\n## Süreç Adımları\n### PA-001: Giriş\nKullanıcı giriş yapar.\n"
      "### PA-002: Onay\nY.\n\n## Açık Sorular\n| Q-001 |\n")
sa = ra.bolum_bul(MD, "Süreç Adımları")
dogru("PA-001" in sa["icerik"] and "Açık Sorular" not in sa["icerik"], "üst bölüm alt PA'ları kapsar")
pa1 = ra.bolum_bul(MD, "PA-001")
dogru("PA-002" not in pa1["icerik"], "PA-001 tekil")
esit(ra.bolum_bul(MD, "YOK"), None, "bulunamayan None")

(tmp / "t.md").write_text(MD, encoding="utf-8")
rv = ra.bolum_duzenle("t.md", "PA-001", "2fa ekle",
                      _ai_fn=lambda t, b: "### PA-001: Giriş\nE-posta + 2FA (DÜZENLENDİ).\n")
v2 = r.versiyon_icerik("t.md", "v2")
dogru("DÜZENLENDİ" in v2 and "PA-002" in v2 and v2.count("### PA-001") == 1, "splice komşuları korur")
esit(rv["onay_durumu"], "beklemede", "bölüm düzenleme beklemede")

print(f"\nREVİZYON TESTLERİ GEÇTİ ({ok} assert)")
