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

analiz_cagrilari: list = []      # gorev_analiz_et'e geçen ekran_baglami'yı yakala
analiz_girdi: list = []          # (cevaplar, onceki_sorular, description) — cevap/özyineleme testi

jk.gorev_getir = lambda key: {"key": key, "summary": f"{key} başlık", "description": "açıklama"}


def _sahte_analiz(gorev, cevaplar="", onceki_sorular="", **kw):
    analiz_cagrilari.append(kw.get("ekran_baglami", "YOK"))
    analiz_girdi.append({"cevaplar": cevaplar, "onceki": onceki_sorular, "desc": gorev.get("description", "")})
    acik = "Açık soru tespit edilmedi." if cevaplar else "Q-T-001: belirsizlik var?"
    return {"markdown": f"# Analiz {gorev['key']}\n\n(cevap: {cevaplar or 'yok'})", "acik_sorular": acik}


jk.gorev_analiz_et = _sahte_analiz
jk.gorev_analiz_duzelt = lambda gorev, mevcut, talimat: f"{mevcut}\n\n[DÜZELTİLDİ: {talimat}]"
jk.gorev_jiraya_yaz = lambda key, md: yazilan_aciklama.__setitem__(key, md) or True
jk._iliskili_task_onerileri = lambda md, gorev: [
    {"summary": "BE endpoint ekle", "description": "market servisi", "katman": "BE"},
    {"summary": "FE filtre kaldır", "description": "gereksiz filtre", "katman": "FE"},
]
jk._proje_bilgi = lambda proje, cloud_id: {"task_id": "10001", "story_id": "10002"}
jk._cloud_id = lambda: "cloud-x"
jk._canli_gorev_baglam = lambda gorev: None   # live-app config'e bağlı kalma (offline)


def _sahte_issue_olustur(summary, adf, type_id, proje, cloud_id, parent_key=None):
    key = f"{proje}-{900 + len(acilan_tasklar)}"
    acilan_tasklar.append({"key": key, "summary": summary, "proje": proje})
    return key


jk._issue_olustur = _sahte_issue_olustur
jk.jira_issue_link = lambda inw, outw, tip="Relates": kurulan_linkler.append((inw, outw, tip)) or True

PFX = "/analyst_agent"


# ── analiz → task GÖVDESİNE yazar (yoruma değil), orijinal korunur (#1) ───────
durum: dict = {}
r = jk._komut_uygula("analiz", "", "MBSTRADE-1", PFX, durum)
kontrol("analiz sonucu task GÖVDESİNE yazıldı", "MBSTRADE-1" in yazilan_aciklama)
govde = yazilan_aciklama["MBSTRADE-1"]
kontrol("gövdede orijinal talep + analiz bölümü", "Orijinal Talep" in govde and "Teknik Analiz" in govde)
kontrol("analiz yorumu = gövdeye yazıldı bilgisi", "açıklamasına yazıldı" in r.lower() or "açıklamaya yaz" in r.lower())
kontrol("analiz çıktısı önbelleğe alındı", durum.get("son_analiz", {}).get("MBSTRADE-1", {}).get("md"))
kontrol("bridge analizi KENDİ KENDİNE YETERLİ (ekran_baglami=False)", analiz_cagrilari[-1] is False)

# ── güncelle → SON analizi gövdeye YENİDEN yazar (taslak DEĞİL, 0-token) ──────
yazilan_aciklama.clear()
oncesi = len(analiz_cagrilari)
r = jk._komut_uygula("guncelle", "", "MBSTRADE-1", PFX, durum)
kontrol("güncelle gövdeye yazdı, taslak oluşturmadı",
        "MBSTRADE-1" in yazilan_aciklama and "MBSTRADE-1" not in durum.get("taslaklar", {}))
kontrol("güncelle taze önbelleği kullandı (yeniden analiz yok)", len(analiz_cagrilari) == oncesi)

# ── onayla → bekleyen ilişkili taslak yok ────────────────────────────────────
r = jk._komut_uygula("onayla", "", "MBSTRADE-1", PFX, durum)
kontrol("bekleyen taslak yokken onayla no-op", "bekleyen taslak yok" in r)

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

# ── iptal → ilişkili taslağı düşürür ─────────────────────────────────────────
jk._komut_uygula("iliskili-ac", "", "MBSTRADE-3", PFX, durum)
r = jk._komut_uygula("iptal", "", "MBSTRADE-3", PFX, durum)
kontrol("iptal bekleyen taslağı düşürdü", "MBSTRADE-3" not in durum.get("taslaklar", {}) and "iptal edildi" in r.lower())

# ── #3: task'tan RAG anahtar kelimeleri çıkar ────────────────────────────────
kws = jk._task_keywords({"summary": "Prematch Program free-text search input",
                         "description": "freeText parametresi elastic search ile debounced"})
kontrol("task keyword'leri çıkarıldı (durak kelimeler elenmiş)",
        "search" in kws and "elastic" in kws and "için" not in kws)

# ── #1: orijinal talep ayıklama (tekrar analizde korunur) ────────────────────
onceki = "## 📌 Orijinal Talep\n\nfree-text search isteniyor\n\n---\n\n## 🤖 Teknik Analiz (Analyst Agent)\n\neski analiz"
kontrol("orijinal talep tekrar analizde korunur", jk._orijinal_talep_ayikla(onceki) == "free-text search isteniyor")

# ── özyineleme önlemi: analiz GİRDİSİ orijinal talep (gövde değil) ────────────
og = jk._orijinal_gorev({"key": "MBSTRADE-9", "summary": "s",
                         "description": "## 📌 Orijinal Talep\n\nORJ metin\n\n---\n\n## 🤖 Teknik Analiz (Analyst Agent)\n\nESKİ ANALİZ"})
kontrol("gövdeye analiz yazılmışsa girdi = orijinal talep", og["description"] == "ORJ metin")
kontrol("gövdeden analiz bölümü ayıklanır (düzelt için)",
        jk._analiz_bolumu_ayikla("## 📌 Orijinal Talep\n\nX\n\n---\n\n## 🤖 Teknik Analiz (Analyst Agent)\n\nANALİZ GÖVDESİ") == "ANALİZ GÖVDESİ")

# ── cevap → analizi cevaplarla YENİDEN üretir, soruları yakınsar, gövdeye yazar ──
durum2: dict = {}
jk._komut_uygula("analiz", "", "MBSTRADE-5", PFX, durum2)
kontrol("analiz açık soruyu önbelleğe aldı", "Q-T-001" in durum2["son_analiz"]["MBSTRADE-5"].get("acik", ""))
kontrol("analiz girdisi orijinal (gövde değil)", analiz_girdi[-1]["desc"] == "açıklama")
yazilan_aciklama.clear()
r = jk._komut_uygula("cevap", "Q-T-001: Event Name korunur", "MBSTRADE-5", PFX, durum2)
kontrol("cevap gövdeyi güncelledi", "MBSTRADE-5" in yazilan_aciklama)
kontrol("cevap önceki soruları yakınsamaya geçirdi", "Q-T-001" in analiz_girdi[-1]["onceki"])
kontrol("cevap → açık soru kalmadı bilgisi", "açık soru kalmadı" in r.lower())

# ── düzelt → yalnız ilgili kısmı düzeltir, gövdeye yazar ──────────────────────
yazilan_aciklama.clear()
r = jk._komut_uygula("duzelt", "§7'ye debounce süresi ekle", "MBSTRADE-5", PFX, durum2)
kontrol("düzelt ilgili kısmı düzeltip gövdeye yazdı",
        "MBSTRADE-5" in yazilan_aciklama and "DÜZELTİLDİ" in yazilan_aciklama["MBSTRADE-5"])

# ── döngü koruması: kendi 🤖 yanıtımız komut sayılmaz ────────────────────────
kontrol("kendi yanıtı komut değil", jk._komut_coz(jk.ROBOT_IMZA + " ✅ güncellendi", PFX) is None)

print(f"\nJIRA KÖPRÜSÜ TESTLERİ GEÇTİ ({basari} kontrol)")
