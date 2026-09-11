"""Jira Köprüsü — offline durum-makinesi testi (0 token, ağ YOK).

Tüm Jira/AI çağrıları monkeypatch'lenir; yalnız komut→taslak→onay akışının
mantığı doğrulanır. Çalıştır:  venv/bin/python tests/test_jira_kopru.py
"""

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("AUTH_ENABLED", "false")

import skills.jira_kopru as jk  # noqa: E402

basari = 0


def kontrol(ad: str, kosul: bool) -> None:
    global basari
    if not kosul:
        raise SystemExit(f"FAIL {ad}")
    basari += 1
    print(f"  ✓ {ad}")


# ── Sahte Jira/AI dünyası ────────────────────────────────────────────────────
yazilan_aciklama: dict = {}      # key → güncellenen açıklama md
acilan_tasklar: list = []        # oluşturulan issue'lar
kurulan_linkler: list = []       # (inward, outward, tip)

jk.gorev_getir = lambda key: {"key": key, "summary": f"{key} başlık", "description": "açıklama"}
jk.gorev_analiz_et = lambda gorev, cevaplar="", **kw: {
    "markdown": f"# Analiz {gorev['key']}\n\n(cevap arg: {cevaplar or 'yok'})", "acik_sorular": ""}
jk.gorev_jiraya_yaz = lambda key, md: yazilan_aciklama.__setitem__(key, md) or True
jk._iliskili_task_onerileri = lambda md, gorev: [
    {"summary": "BE endpoint ekle", "description": "market servisi", "katman": "BE"},
    {"summary": "FE filtre kaldır", "description": "gereksiz filtre", "katman": "FE"},
]
jk._proje_bilgi = lambda proje, cloud_id: {"task_id": "10001", "story_id": "10002"}
jk._cloud_id = lambda: "cloud-x"


def _sahte_issue_olustur(summary, adf, type_id, proje, cloud_id, parent_key=None):
    key = f"{proje}-{900 + len(acilan_tasklar)}"
    acilan_tasklar.append({"key": key, "summary": summary, "proje": proje})
    return key


jk._issue_olustur = _sahte_issue_olustur
jk.jira_issue_link = lambda inw, outw, tip="Relates": kurulan_linkler.append((inw, outw, tip)) or True

PFX = "/analyst_agent"


# ── analiz → önbellek ────────────────────────────────────────────────────────
durum: dict = {}
r = jk._komut_uygula("analiz", "", "MBSTRADE-1", PFX, durum)
kontrol("analiz yorumu üretiliyor", "Teknik Analiz" in r and "MBSTRADE-1" in r)
kontrol("analiz çıktısı önbelleğe alındı", durum.get("son_analiz", {}).get("MBSTRADE-1", {}).get("md"))

# ── güncelle → taslak (henüz YAZILMADI) ──────────────────────────────────────
r = jk._komut_uygula("guncelle", "", "MBSTRADE-1", PFX, durum)
kontrol("güncelle taslağı oluşturuldu", durum["taslaklar"]["MBSTRADE-1"]["tip"] == "guncelle")
kontrol("güncelle taslakken açıklama YAZILMADI", "MBSTRADE-1" not in yazilan_aciklama)
kontrol("güncelle önizleme + onay ipucu", "onayla" in r)

# ── onayla → açıklama yazılır, taslak düşer ──────────────────────────────────
r = jk._komut_uygula("onayla", "", "MBSTRADE-1", PFX, durum)
kontrol("onayla açıklamayı yazdı", "MBSTRADE-1" in yazilan_aciklama)
kontrol("onaydan sonra taslak temizlendi", "MBSTRADE-1" not in durum.get("taslaklar", {}))

# ── ikinci onayla → bekleyen taslak yok (çift-uygulama önlemi) ────────────────
yazilan_aciklama.clear()
r = jk._komut_uygula("onayla", "", "MBSTRADE-1", PFX, durum)
kontrol("ikinci onayla no-op (bekleyen taslak yok)", "bekleyen taslak yok" in r and "MBSTRADE-1" not in yazilan_aciklama)

# ── ilişkili-aç → taslak (henüz task AÇILMADI) ───────────────────────────────
r = jk._komut_uygula("iliskili-ac", "", "MBSTRADE-2", PFX, durum)
kontrol("ilişkili-aç taslağı 2 öneri", len(durum["taslaklar"]["MBSTRADE-2"]["oneriler"]) == 2)
kontrol("ilişkili-aç taslakken task AÇILMADI", not acilan_tasklar)

# ── onayla → task'lar açılır + Relates bağlanır ──────────────────────────────
r = jk._komut_uygula("onayla", "", "MBSTRADE-2", PFX, durum)
kontrol("2 ilişkili task açıldı", len(acilan_tasklar) == 2)
kontrol("açılan task'lar doğru projede", all(t["proje"] == "MBSTRADE" for t in acilan_tasklar))
kontrol("her yeni task kaynağa Relates bağlandı",
        len(kurulan_linkler) == 2 and all(o == "MBSTRADE-2" and t == "Relates" for _, o, t in kurulan_linkler))
kontrol("ilişkili-aç onayından sonra taslak temizlendi", "MBSTRADE-2" not in durum.get("taslaklar", {}))

# ── iptal → taslağı düşürür ──────────────────────────────────────────────────
jk._komut_uygula("guncelle", "", "MBSTRADE-3", PFX, durum)
r = jk._komut_uygula("iptal", "", "MBSTRADE-3", PFX, durum)
kontrol("iptal bekleyen taslağı düşürdü", "MBSTRADE-3" not in durum.get("taslaklar", {}) and "iptal edildi" in r.lower())

# ── döngü koruması: kendi 🤖 yanıtımız komut sayılmaz ────────────────────────
kontrol("kendi yanıtı komut değil", jk._komut_coz(jk.ROBOT_IMZA + " ✅ güncellendi", PFX) is None)

print(f"\nJIRA KÖPRÜSÜ TESTLERİ GEÇTİ ({basari} kontrol)")
