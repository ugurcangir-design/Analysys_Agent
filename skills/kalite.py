"""
Çıktı Kalite Skoru — analiz dosyasını otomatik puanlar.

Analist çıktının kalitesini hemen görür; düşük puanlı alanları AI ile
düzeltmek için Yeniden Çalıştır + hedefli düzeltme notu kullanılır.

Skor: 0-100 arası, 100'den başlayıp eksikliklere göre azalır.
Renk:  90+ yeşil · 75-89 sarı · 60-74 turuncu · <60 kırmızı
"""

import re

from .base import OUTPUT_DIR


# ─── Tespit Desenleri ────────────────────────────────────────────────────────

_BELIRSIZ_ETIKET = re.compile(r"\[K:\s*❓\s*Belirsiz[^\]]*\]", re.IGNORECASE)
_VARSAYIM_ETIKET = re.compile(r"⚠\s*VARSAYIM", re.IGNORECASE)
_KAYNAK_ETIKET   = re.compile(r"\[K:\s*[^\]]+\]")

# Süreç/teknik ID'ler — kaynaksız oran hesaplaması için
_TUM_ID = re.compile(r"\b(BR-\d+|AC-\d+|PA-\d+|EF-\d+|AF-\d+|EK-\d+|FR-\d+|NFR-\d+|US-\d+|I-\d+|T-FE-\d+|T-BE-\d+|YE-\d+|KL-\d+|DG-\d+|Q-T?-?\d+|PO-\d+)\b")

# Yasak ifadeler (RAG ilkesine aykırı belirsiz ifadeler)
_YASAK_IFADELER = [
    r"\bgenelde\b",
    r"\bmuhtemelen\b",
    r"\bkullanıcı dostu\b",
    r"\bhızlı olmalı\b",
    r"\bperformanslı olmalı\b",
    r"\bbir şekilde\b",
    r"\bgenellikle\b",
    r"\bbüyük ihtimalle\b",
    r"\bgerektiği gibi\b",
    r"\bdoğru biçimde\b",
    r"\bsistem otomatik\b(?!\s+olarak)",  # "sistem otomatik yapar" gibi muğlak
]
_YASAK_REGEX = re.compile("|".join(_YASAK_IFADELER), re.IGNORECASE)

# Açık soru blokları — durum belirleme için Q-T-XXX vs Q-XXX
_ACIK_SORU_BLOK = re.compile(r"^###\s+(Q-T?-?\d+|PO-\d+|Q-K-\d+)", re.MULTILINE)
_ACIK_SORU_TABLO = re.compile(r"^\|\s*(Q-\d+)\s*\|[^|]*\|[^|]*\|\s*(Kritik|Yüksek|Orta|Düşük)", re.MULTILINE | re.IGNORECASE)

# Teknik analize özgü bölümler
_DDL_BLOK = re.compile(r"```sql\s+CREATE\s+TABLE", re.IGNORECASE)
_YAML_BLOK = re.compile(r"```ya?ml\s+[^\n]*?(?:paths|/api/|openapi)", re.IGNORECASE)
_BOLUM17 = re.compile(r"^##\s+17\.\s+İş Kırılımı", re.MULTILINE)
_IZLENEBILIRLIK = re.compile(r"^##\s+\d+\.\s+İzlenebilirlik", re.MULTILINE)


# ─── Skor Hesaplama ───────────────────────────────────────────────────────────

def _oncelik_skoru(satir: str) -> int:
    """Açık soru tablo satırı veya bloğundaki önceliği -puan değerine çevirir."""
    s = satir.lower()
    if "kritik" in s: return 5
    if "yüksek" in s or "yuksek" in s: return 3
    if "orta" in s: return 1
    return 0


def cikti_skoru(dosya_adi: str) -> dict:
    """Bir output dosyasını puanlar.

    Returns:
        {
            "ok": bool,
            "skor": int (0-100),
            "renk": str (yesil/sari/turuncu/kirmizi),
            "metrikler": dict (ham sayılar),
            "sorunlar": list[dict] — her bulguda etki + örnek
        }
    """
    yol = OUTPUT_DIR / dosya_adi
    if not yol.exists():
        return {"ok": False, "error": f"{dosya_adi} bulunamadı"}

    metin = yol.read_text(encoding="utf-8", errors="replace")
    teknik = dosya_adi == "teknik-analiz.md"

    sorunlar: list[dict] = []
    skor = 100

    # 1) Belirsiz etiketler [K: ❓ Belirsiz]
    belirsizler = _BELIRSIZ_ETIKET.findall(metin)
    if belirsizler:
        ceza = min(len(belirsizler) * 3, 30)
        skor -= ceza
        sorunlar.append({
            "tip": "belirsiz_iddia",
            "adet": len(belirsizler),
            "ceza": ceza,
            "aciklama": f"{len(belirsizler)} adet kaynaksız (belirsiz) iddia var. RAG ilkesi gereği bunlar Açık Sorular'a taşınmalı.",
            "ornek": belirsizler[0] if belirsizler else None,
        })

    # 2) Varsayım etiketleri
    varsayimlar = _VARSAYIM_ETIKET.findall(metin)
    if varsayimlar:
        ceza = min(len(varsayimlar), 10)
        skor -= ceza
        sorunlar.append({
            "tip": "varsayim",
            "adet": len(varsayimlar),
            "ceza": ceza,
            "aciklama": f"{len(varsayimlar)} varsayım yapılmış. Bunlar onaylanmadıkça çıktı yarı-resmi sayılır.",
        })

    # 3) Açık sorular (öncelik bazlı)
    soru_cezasi = 0
    soru_sayisi = {"kritik": 0, "yuksek": 0, "orta": 0, "dusuk": 0}

    # 3a) Blok formatı (### Q-T-XXX)
    for m in _ACIK_SORU_BLOK.finditer(metin):
        baslangic = m.end()
        bitis = metin.find("\n##", baslangic)
        if bitis == -1: bitis = baslangic + 800
        blok = metin[baslangic:bitis]
        oncelik_m = re.search(r"Öncelik\s*:\s*(Kritik|Yüksek|Orta|Düşük)", blok, re.IGNORECASE)
        if oncelik_m:
            puan = _oncelik_skoru(oncelik_m.group(1))
            soru_cezasi += puan
            if puan == 5: soru_sayisi["kritik"] += 1
            elif puan == 3: soru_sayisi["yuksek"] += 1
            elif puan == 1: soru_sayisi["orta"] += 1
            else: soru_sayisi["dusuk"] += 1
    # 3b) Tablo formatı
    for m in _ACIK_SORU_TABLO.finditer(metin):
        oncelik = m.group(2)
        puan = _oncelik_skoru(oncelik)
        soru_cezasi += puan
        if puan == 5: soru_sayisi["kritik"] += 1
        elif puan == 3: soru_sayisi["yuksek"] += 1
        elif puan == 1: soru_sayisi["orta"] += 1

    if soru_cezasi:
        ceza = min(soru_cezasi, 35)
        skor -= ceza
        ozet = []
        if soru_sayisi["kritik"]: ozet.append(f"{soru_sayisi['kritik']} kritik")
        if soru_sayisi["yuksek"]: ozet.append(f"{soru_sayisi['yuksek']} yüksek")
        if soru_sayisi["orta"]:   ozet.append(f"{soru_sayisi['orta']} orta")
        sorunlar.append({
            "tip": "acik_soru",
            "adet": sum(soru_sayisi.values()),
            "ceza": ceza,
            "aciklama": f"Açık sorular: {', '.join(ozet) if ozet else 'çeşitli'}. Cevap geldikçe analiz güçlenir.",
        })

    # 4) Yasak ifadeler
    yasaklar = _YASAK_REGEX.findall(metin)
    if yasaklar:
        ceza = min(len(yasaklar) * 2, 20)
        skor -= ceza
        ornekler = list(set(yasaklar[:5]))
        sorunlar.append({
            "tip": "yasak_ifade",
            "adet": len(yasaklar),
            "ceza": ceza,
            "aciklama": f"{len(yasaklar)} adet muğlak ifade. RAG ilkesi gereği bunlar netleştirilmeli.",
            "ornek": ", ".join(ornekler),
        })

    # 5) Kaynaksız ID oranı
    tum_idler = set(_TUM_ID.findall(metin))
    if len(tum_idler) >= 5:
        # Her ID için: ya satırında ya bağlamında [K: ...] olmalı
        kaynakli_say = 0
        for id_ in tum_idler:
            # ID'nin geçtiği satıra bak; aynı satırda [K: ...] varsa kaynaklı
            for satir in metin.split("\n"):
                if id_ in satir and _KAYNAK_ETIKET.search(satir):
                    kaynakli_say += 1
                    break
        oran = kaynakli_say / len(tum_idler)
        if oran < 0.5:
            ceza = min(int((0.5 - oran) * 30), 15)
            skor -= ceza
            sorunlar.append({
                "tip": "kaynaksiz_id",
                "adet": len(tum_idler) - kaynakli_say,
                "ceza": ceza,
                "aciklama": f"ID'lerin %{int(oran*100)}'i kaynaklı; en az %50 olmalı. "
                            f"Her ID için satır içinde [K: ...] etiketi bekleniyor.",
            })

    # 6) İzlenebilirlik matrisi
    if not _IZLENEBILIRLIK.search(metin):
        skor -= 10
        sorunlar.append({
            "tip": "izlenebilirlik_yok",
            "ceza": 10,
            "aciklama": "İzlenebilirlik Matrisi bölümü bulunamadı. Aşamalar arası ID takibi için zorunlu.",
        })

    # 7) Teknik analize özgü kontroller
    if teknik:
        if not _DDL_BLOK.search(metin):
            skor -= 10
            sorunlar.append({
                "tip": "ddl_yok",
                "ceza": 10,
                "aciklama": "Çalıştırılabilir DDL bloğu (```sql CREATE TABLE ...) bulunamadı.",
            })
        if not _YAML_BLOK.search(metin):
            skor -= 10
            sorunlar.append({
                "tip": "yaml_yok",
                "ceza": 10,
                "aciklama": "OpenAPI YAML bloğu (```yaml /api/... veya paths:) bulunamadı.",
            })
        if not _BOLUM17.search(metin):
            skor -= 10
            sorunlar.append({
                "tip": "is_kirilimi_yok",
                "ceza": 10,
                "aciklama": "Bölüm 17 (İş Kırılımı — T-FE/T-BE) yok. Jira hiyerarşi üretimi etkilenir.",
            })

    # Skor alt sınırı
    skor = max(skor, 0)

    # Renk eşikleri
    if skor >= 90:
        renk = "yesil"
    elif skor >= 75:
        renk = "sari"
    elif skor >= 60:
        renk = "turuncu"
    else:
        renk = "kirmizi"

    return {
        "ok": True,
        "dosya": dosya_adi,
        "skor": skor,
        "renk": renk,
        "metrikler": {
            "uzunluk_karakter": len(metin),
            "id_sayisi": len(tum_idler),
            "belirsiz_iddia": len(belirsizler),
            "varsayim": len(varsayimlar),
            "acik_soru_kritik": soru_sayisi.get("kritik", 0),
            "acik_soru_yuksek": soru_sayisi.get("yuksek", 0),
            "acik_soru_orta": soru_sayisi.get("orta", 0),
            "yasak_ifade": len(yasaklar),
        },
        "sorunlar": sorunlar,
    }


def duzeltme_notu_uret(skor_sonucu: dict) -> str:
    """Skor sonucundan, sorunları gideren Yeniden Çalıştır düzeltme notu üretir."""
    sorunlar = skor_sonucu.get("sorunlar", [])
    if not sorunlar:
        return "Çıktıda iyileştirilecek tespit yok."

    parcalar = [
        "Aşağıdaki kalite sorunlarını düzelt — diğer bölümleri DEĞİŞTİRME:",
        "",
    ]
    for s in sorunlar:
        tip = s["tip"]
        if tip == "belirsiz_iddia":
            parcalar.append(f"- {s['adet']} adet `[K: ❓ Belirsiz]` etiketli iddia var. "
                          "Bunları ana metinden çıkar ve `Açık Sorular` bölümüne soru olarak taşı.")
        elif tip == "yasak_ifade":
            parcalar.append(f"- Muğlak ifadeler (örn. {s.get('ornek','genelde')}): bunları "
                          "ölçülebilir/test edilebilir hale getir veya Açık Sorular'a soru olarak taşı.")
        elif tip == "kaynaksiz_id":
            parcalar.append(f"- {s['adet']} ID kaynaksız. Her ID için satır içinde `[K: <kaynak>]` "
                          "etiketi ekle (BRD §X, Swagger:..., Confluence:..., Jira:KEY-X).")
        elif tip == "izlenebilirlik_yok":
            parcalar.append("- İzlenebilirlik Matrisi bölümü eklenmemiş. Çıktının sonuna ekle: "
                          "her aşamadaki ID'nin bu çıktıdaki karşılığını listele.")
        elif tip == "ddl_yok":
            parcalar.append("- Veri Modeli bölümünde çalıştırılabilir ```sql CREATE TABLE ...``` "
                          "blokları yok. Her tablo için gerçek DDL ekle.")
        elif tip == "yaml_yok":
            parcalar.append("- API bölümünde ```yaml OpenAPI 3.0 endpoint blokları yok. "
                          "Her endpoint için gerçek YAML şeması ekle.")
        elif tip == "is_kirilimi_yok":
            parcalar.append("- Bölüm 17 İş Kırılımı (T-FE/T-BE görev tablosu) eksik. Ekle.")
        # varsayım ve açık_soru için otomatik düzeltme önerme — kullanıcı yapmalı

    return "\n".join(parcalar)
