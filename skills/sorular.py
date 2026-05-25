"""
Soru Defteri — analiz çıktılarındaki açık soruları kalıcı kayda alır.

İş akışı:
1. Analiz tamamlanır (surec/teknik/brd) — çıktıda açık sorular bölümü olur
2. `parse_ve_birlestir()` çağrılır — sorular `output/sorular.json`'a eklenir
   - Mevcut soru varsa (id + kaynak_dosya eşleşmesi) durum/cevap/varsayım korunur
   - Yeni soru "acik" olarak eklenir
   - Çıktıdan kaybolan eski sorular silinmez (analist cevaplamış olabilir)
3. Analist UI'dan her soruya 4 işlem yapabilir:
   - cevapla: cevap metni gir → durum=cevaplandi
   - varsayim: AI varsayım üretir → durum=varsayim
   - beklet: cevap sonra → durum=bekleniyor
   - atla: gereksiz → durum=atlandi
4. Cevap geldiğinde refine sistemi tetiklenir, etkilenen bölüm güncellenir.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .base import OUTPUT_DIR


SORULAR_DOSYA = OUTPUT_DIR / "sorular.json"

# Geçerli durum değerleri
DURUM_DEGERLERI = frozenset({"acik", "bekleniyor", "cevaplandi", "atlandi", "varsayim"})

# Hangi çıktı dosyalarından soru çekilir
# (analiz formatımızda Q-T-XXX, PO-XXX gibi yapılandırılmış sorular var)
KAYNAK_DOSYALAR = (
    "teknik-analiz.md",   # Q-T-XXX
    "brd-sorular.md",     # PO-XXX
    "acik-sorular.md",    # Q-T-XXX (combined output'tan)
    "surec-analizi.md",   # bölüm 12 tablosu (Q-XXX)
)


# ─── JSON Storage ─────────────────────────────────────────────────────────────

def sorular_yukle() -> dict:
    """Mevcut soru defterini döndürür. Yoksa boş şablon."""
    if SORULAR_DOSYA.exists():
        try:
            return json.loads(SORULAR_DOSYA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sorular": [], "son_parse": None}


def sorular_kaydet(data: dict) -> None:
    """Atomik yazım: tmp → replace."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SORULAR_DOSYA.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SORULAR_DOSYA)


# ─── Markdown Parser ──────────────────────────────────────────────────────────

# Yapılandırılmış soru bloğu deseni:
# ### Q-T-001: Başlık     veya     ### PO-1: Başlık
#  ... satırlar ...
# (boş satır veya yeni ### bloğu)
_SORU_BAS = re.compile(r"^###\s+(Q-T-\d+|Q-\d+|PO-\d+|Q-K-\d+)\s*:?\s*(.*?)\s*$", re.MULTILINE)


def _alan_oku(blok: str, anahtar: str) -> str:
    """Bloktan '- Anahtar: değer' formatında satırı çeker."""
    desen = re.compile(rf"^[\s\*\-]*\*?\*?{re.escape(anahtar)}\*?\*?\s*:\s*(.+?)$", re.MULTILINE | re.IGNORECASE)
    m = desen.search(blok)
    return m.group(1).strip() if m else ""


def parse_md_sorular(md_yol: Path) -> list[dict]:
    """Bir .md dosyasından yapılandırılmış soru bloklarını çıkarır.

    Şu formatları destekler:
    - Q-T-XXX (teknik analiz)
    - Q-XXX (süreç analizi)
    - PO-XXX (BRD soruları)
    - Q-K-XXX (kapsam analizi — gelecekteki kullanım)
    """
    if not md_yol.exists():
        return []
    try:
        metin = md_yol.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    sonuc: list[dict] = []
    # Tüm soru başlangıçlarını bul, blokları çıkar
    eslesmeler = list(_SORU_BAS.finditer(metin))
    for i, m in enumerate(eslesmeler):
        soru_id = m.group(1)
        baslik = m.group(2).strip()
        baslangic = m.end()
        bitis = eslesmeler[i + 1].start() if i + 1 < len(eslesmeler) else len(metin)
        # Bir sonraki ## (üst başlık) öncesinde dur
        ust_baslik = re.search(r"\n##\s", metin[baslangic:bitis])
        if ust_baslik:
            bitis = baslangic + ust_baslik.start()
        blok = metin[baslangic:bitis]

        sonuc.append({
            "id": soru_id,
            "kaynak_dosya": md_yol.name,
            "baslik": baslik or _alan_oku(blok, "Soru")[:80] or soru_id,
            "kategori": _alan_oku(blok, "Kategori"),
            "katman": _alan_oku(blok, "Katman"),
            "oncelik": _alan_oku(blok, "Öncelik") or _alan_oku(blok, "Onem"),
            "bagli_id": _alan_oku(blok, "Bağlı ID") or _alan_oku(blok, "Bağlı Süreç ID")
                         or _alan_oku(blok, "Bağlı Gereksinim") or _alan_oku(blok, "Bağlı"),
            "soru": _alan_oku(blok, "Soru"),
            "mevcut_durum": _alan_oku(blok, "Mevcut Bilgi") or _alan_oku(blok, "Mevcut Durum"),
            "beklenen_yanit": _alan_oku(blok, "Beklenen Yanıt"),
            "sorumlu": _alan_oku(blok, "Sorumlu"),
            "etki": _alan_oku(blok, "Etki"),
        })
    return sonuc


# ─── Birleştirme (Merge) ──────────────────────────────────────────────────────

def parse_ve_birlestir() -> dict:
    """Tüm kaynak çıktıları tara, mevcut soru defteriyle birleştir.

    Birleştirme kuralları:
    - id + kaynak_dosya eşleşen mevcut soru: durum/cevap/varsayım/güncellenme KORUNUR,
      yeni içerik (soru metni vb.) güncellenir
    - Yeni soru: "acik" durumuyla eklenir
    - Çıktıdan kaybolan eski soru: SİLİNMEZ (analist cevaplamış olabilir; durum=kapandi gibi
      işaretlenmedi — analist bilinçli atla/cevapla seçtiyse zaten görünmez)
    """
    mevcut = sorular_yukle()
    indeks = {(s["id"], s["kaynak_dosya"]): s for s in mevcut.get("sorular", [])}

    simdi = datetime.now().isoformat(timespec="seconds")
    yeni_listesi = []
    eklenen = 0
    guncellenen = 0

    for dosya_adi in KAYNAK_DOSYALAR:
        for parsed in parse_md_sorular(OUTPUT_DIR / dosya_adi):
            anahtar = (parsed["id"], parsed["kaynak_dosya"])
            eski = indeks.pop(anahtar, None)
            if eski:
                # Korunan alanlar (analist veri girmişse bozma)
                parsed["durum"]      = eski.get("durum", "acik")
                parsed["cevap"]      = eski.get("cevap")
                parsed["varsayim"]   = eski.get("varsayim")
                parsed["olusturuldu_at"] = eski.get("olusturuldu_at", simdi)
                parsed["guncellendi_at"] = simdi
                guncellenen += 1
            else:
                parsed["durum"] = "acik"
                parsed["cevap"] = None
                parsed["varsayim"] = None
                parsed["olusturuldu_at"] = simdi
                parsed["guncellendi_at"] = simdi
                eklenen += 1
            yeni_listesi.append(parsed)

    # Çıktıda artık olmayan eski sorular — koruyalım (kaynak dosya silindi olabilir)
    for kalanlar in indeks.values():
        yeni_listesi.append(kalanlar)

    yeni_veri = {
        "sorular": yeni_listesi,
        "son_parse": simdi,
        "istatistik": istatistik_hesapla(yeni_listesi),
        "_son_islem": {"eklenen": eklenen, "guncellenen": guncellenen},
    }
    sorular_kaydet(yeni_veri)
    return yeni_veri


# ─── Tek Soru Güncelleme ──────────────────────────────────────────────────────

def soru_guncelle(
    soru_id: str,
    kaynak_dosya: str,
    durum: str,
    cevap: str | None = None,
    varsayim: str | None = None,
) -> dict:
    """Tek bir sorunun durumunu/cevabını günceller.

    Returns:
        Güncellenmiş soru dict'i. Bulunamazsa ValueError.
    """
    if durum not in DURUM_DEGERLERI:
        raise ValueError(f"Geçersiz durum: {durum}. Kabul edilen: {sorted(DURUM_DEGERLERI)}")

    data = sorular_yukle()
    sorular = data.get("sorular", [])
    hedef = None
    for s in sorular:
        if s.get("id") == soru_id and s.get("kaynak_dosya") == kaynak_dosya:
            hedef = s
            break
    if not hedef:
        raise ValueError(f"Soru bulunamadı: {soru_id} / {kaynak_dosya}")

    hedef["durum"] = durum
    if cevap is not None:
        hedef["cevap"] = cevap.strip() or None
    if varsayim is not None:
        hedef["varsayim"] = varsayim.strip() or None
    hedef["guncellendi_at"] = datetime.now().isoformat(timespec="seconds")

    data["sorular"] = sorular
    data["istatistik"] = istatistik_hesapla(sorular)
    sorular_kaydet(data)
    return hedef


def soru_sil(soru_id: str, kaynak_dosya: str) -> bool:
    """Bir soruyu defterinden tamamen kaldırır. True = silindi."""
    data = sorular_yukle()
    sorular = data.get("sorular", [])
    yeni = [s for s in sorular if not (s.get("id") == soru_id and s.get("kaynak_dosya") == kaynak_dosya)]
    if len(yeni) == len(sorular):
        return False
    data["sorular"] = yeni
    data["istatistik"] = istatistik_hesapla(yeni)
    sorular_kaydet(data)
    return True


# ─── İstatistik ───────────────────────────────────────────────────────────────

def istatistik_hesapla(sorular: list[dict]) -> dict:
    """Banner için özet sayılar."""
    sayilar = {d: 0 for d in DURUM_DEGERLERI}
    kritik_acik = 0
    uygulanmamis = 0
    for s in sorular:
        d = s.get("durum", "acik")
        sayilar[d] = sayilar.get(d, 0) + 1
        if d in ("acik", "bekleniyor") and (s.get("oncelik") or "").lower().startswith("kritik"):
            kritik_acik += 1
        if d in ("cevaplandi", "varsayim") and not s.get("uygulandi_at"):
            uygulanmamis += 1
    return {
        "toplam": len(sorular),
        "acik": sayilar["acik"],
        "bekleniyor": sayilar["bekleniyor"],
        "cevaplandi": sayilar["cevaplandi"],
        "atlandi": sayilar["atlandi"],
        "varsayim": sayilar["varsayim"],
        "kritik_acik": kritik_acik,
        "uygulanmamis": uygulanmamis,
    }


# ─── Refine Entegrasyonu ──────────────────────────────────────────────────────

def uygulanacak_sorular(zorla: bool = False) -> dict[str, list[dict]]:
    """Cevap/varsayım girilmiş ama analize henüz işlenmemiş soruları döndürür.

    Args:
        zorla: True ise zaten uygulanmış olanları da dahil eder (yeniden uygulama)

    Returns:
        {kaynak_dosya: [sorular]} formatında gruplandırılmış liste
    """
    data = sorular_yukle()
    sonuc: dict[str, list[dict]] = {}
    for s in data.get("sorular", []):
        if s.get("durum") not in ("cevaplandi", "varsayim"):
            continue
        if not zorla and s.get("uygulandi_at"):
            continue
        kaynak = s.get("kaynak_dosya", "")
        if not kaynak:
            continue
        sonuc.setdefault(kaynak, []).append(s)
    return sonuc


def duzeltme_notu_olustur(sorular: list[dict]) -> str:
    """Bir dosyaya ait cevaplanmış soruları refine için düzeltme notuna çevirir."""
    parcalar = [
        "Aşağıdaki açık sorulara analist cevap verdi. Bu cevapları analize işle:",
        "",
        "**Kurallar:**",
        "- CEVAP verilmiş soru: ilgili belirsizliği gideren bilgiyi ana metnin "
        "doğru yerine yerleştir (örn. tablo satırı, kural detayı). Soruyu "
        '"Açık Sorular" bölümünden KALDIR.',
        "- VARSAYIM verilmiş soru: bilgiyi ana metne yerleştirirken başına "
        "`⚠ VARSAYIM:` etiketi ekle. Soruyu açık sorularda BIRAK ve durumunu "
        '"varsayım yapıldı, onaylanması gerekir" notuyla işaretle.',
        "- Cevabın etkilemediği diğer bölümleri DEĞİŞTİRME.",
        "- Cevap kaynak gerektiriyorsa `[K: Analist cevabı]` etiketi kullan.",
        "",
        "**Cevaplar:**",
        "",
    ]
    for s in sorular:
        tip = "VARSAYIM" if s.get("durum") == "varsayim" else "CEVAP"
        icerik = s.get("varsayim") if s.get("durum") == "varsayim" else s.get("cevap")
        parcalar.append(f"### [{s['id']}] ({tip})")
        if s.get("baslik"):
            parcalar.append(f"**Konu:** {s['baslik']}")
        if s.get("bagli_id"):
            parcalar.append(f"**Bağlı ID:** {s['bagli_id']}")
        if s.get("soru"):
            parcalar.append(f"**Orijinal soru:** {s['soru']}")
        parcalar.append(f"**{tip}:** {icerik or '(boş)'}")
        parcalar.append("")
    return "\n".join(parcalar)


def uygulandi_isaretle(soru_id: str, kaynak_dosya: str) -> None:
    """Bir sorunun refine'a uygulandığını işaretler (uygulandi_at timestamp)."""
    data = sorular_yukle()
    for s in data.get("sorular", []):
        if s.get("id") == soru_id and s.get("kaynak_dosya") == kaynak_dosya:
            s["uygulandi_at"] = datetime.now().isoformat(timespec="seconds")
    data["istatistik"] = istatistik_hesapla(data.get("sorular", []))
    sorular_kaydet(data)


# ─── Dış Paylaşım Formatı ─────────────────────────────────────────────────────

def paylasim_metni(durumlar: tuple[str, ...] = ("acik", "bekleniyor")) -> str:
    """Bekleyen/açık soruları kopyala-yapıştır için düz metne dönüştürür.
    (Slack, e-mail, Jira yorumu için kullanılabilir.)
    """
    data = sorular_yukle()
    sorular = [s for s in data.get("sorular", []) if s.get("durum") in durumlar]
    if not sorular:
        return "(Cevap bekleyen soru yok.)"

    # Önceliğe göre sırala
    oncelik_sira = {"kritik": 0, "yüksek": 1, "yuksek": 1, "orta": 2, "düşük": 3, "dusuk": 3}
    sorular.sort(key=lambda s: oncelik_sira.get((s.get("oncelik") or "").lower(), 9))

    satirlar = ["📋 Cevap Bekleyen Sorular", ""]
    for s in sorular:
        satirlar.append(f"• [{s.get('oncelik','?')}] {s['id']}: {s.get('baslik') or s.get('soru','')}")
        if s.get("soru"):
            satirlar.append(f"  Soru: {s['soru']}")
        if s.get("bagli_id"):
            satirlar.append(f"  Bağlı: {s['bagli_id']}")
        if s.get("etki"):
            satirlar.append(f"  Etki: {s['etki']}")
        satirlar.append("")
    return "\n".join(satirlar)
