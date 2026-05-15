"""Kapsam analizi + alternatif süreçler — tek API çağrısında XML combined output."""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    dosya_oku, input_hazirla, referans_brd_oku, ui_kodu_hazirla,
    prompt_yukle,
    OUTPUT_DIR,
    MAX_CHARS_GENEL, MAX_TOKENS_KAPSAM,
)

_KAPSAM_BOLUMLER = """## 1. Özet Değişiklikler
## 2. Yeni Eklenen Gereksinimler
## 3. Kaldırılan Gereksinimler
## 4. Değiştirilen Gereksinimler
## 5. Kapsam Etkisi
## 6. Risk Analizi"""

def kapsam_analizi_yap() -> tuple[Path, Path]:
    print("Kapsam analizi başlatılıyor...")

    revize_icerik, dosya_adi = input_hazirla(is_brd=True)
    print(f"  Revize BRD: {dosya_adi}")

    mevcut_brd = referans_brd_oku()
    if not mevcut_brd:
        raise FileNotFoundError(
            "reference/current-brd/ klasöründe mevcut BRD bulunamadı."
        )

    ui_kodu = ui_kodu_hazirla()
    brd_analiz_dosya = OUTPUT_DIR / "brd-analizi.md"
    ek_baglam = dosya_oku(brd_analiz_dosya, MAX_CHARS_GENEL) if brd_analiz_dosya.exists() else ""

    rol = prompt_yukle("kapsam_analizi_rol")
    bolumler = prompt_yukle("kapsam_analizi_bolumler")
    alt_format = prompt_yukle("kapsam_analizi_alternatifler")

    if ui_kodu:
        ui_hint = "\nMevcut UI kaynak kodu da sağlanmıştır. Her alternatif için 'Mevcut UI'ya Etkisi' bölümü ekle."
        alt_format += "\n### Mevcut UI'ya Etkisi"
        print(f"  UI kodu dahil ediliyor ({len(ui_kodu):,} karakter)...")
    else:
        ui_hint = ""

    sistem = (
        rol + ui_hint + "\n\n"
        "Yanıtını iki XML bloğu halinde ver:\n\n"
        f"<kapsam_analizi>\n{bolumler}\n</kapsam_analizi>\n\n"
        f"<alternatif_surecler>\n3-5 alternatif:\n{alt_format}\n</alternatif_surecler>"
    )

    parcalar = [
        {"type": "text", "text": f"### Mevcut BRD (Baseline)\n\n{mevcut_brd}"},
        *revize_icerik,
    ]
    if ek_baglam:
        parcalar.append({"type": "text", "text": f"### BRD Analizi\n\n{ek_baglam}"})
    if ui_kodu:
        parcalar.append({"type": "text", "text": f"### Mevcut UI Kodu\n\n{ui_kodu}"})
    parcalar.append({"type": "text", "text": "İki BRD'yi karşılaştır, kapsam analizi ve alternatif süreçleri üret."})

    mesajlar = [{"role": "user", "content": parcalar}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_KAPSAM)
    yanit = _metin_sikistir(yanit)

    kapsam     = _xml_ayir(yanit, "kapsam_analizi")
    alternatif = _xml_ayir(yanit, "alternatif_surecler")

    kapsam_yol     = _kaydet("kapsam-analizi.md", kapsam)
    alternatif_yol = _kaydet("alternatif-surecler.md", alternatif)

    return kapsam_yol, alternatif_yol
