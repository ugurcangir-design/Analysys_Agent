"""Kapsam analizi + alternatif süreçler — tek API çağrısında XML combined output."""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    dosya_oku, input_hazirla, referans_brd_oku,
    referans_dosyalari_hazirla, _ref_bloklari_olustur,
    prompt_yukle,
    OUTPUT_DIR,
    MAX_CHARS_GENEL, MAX_TOKENS_KAPSAM,
)


def kapsam_analizi_yap() -> tuple[Path, Path]:
    print("Kapsam analizi başlatılıyor...")

    revize_icerik, dosya_adi = input_hazirla(is_brd=True)
    print(f"  Revize BRD: {dosya_adi}")

    mevcut_brd = referans_brd_oku()
    if not mevcut_brd:
        raise FileNotFoundError(
            "reference/current-brd/ klasöründe mevcut BRD bulunamadı."
        )

    brd_analiz_dosya = OUTPUT_DIR / "brd-analizi.md"
    ek_baglam = dosya_oku(brd_analiz_dosya, MAX_CHARS_GENEL) if brd_analiz_dosya.exists() else ""

    icerik_parcalari: list[dict] = []
    kullanilan_referanslar: list[str] = []

    # Referans kaynakları (Confluence, Jira, Swagger): kapsam değişikliklerinin
    # teknik etki alanını ve geçmiş kararları değerlendirmek için kullanılır.
    ref_dosyalar = referans_dosyalari_hazirla()
    if ref_dosyalar:
        print(f"  {len(ref_dosyalar)} referans dosya dahil ediliyor...")
        ref_bloklari, kullanilan_referanslar = _ref_bloklari_olustur(ref_dosyalar)
        if ref_bloklari:
            ref_bloklari[-1]["cache_control"] = {"type": "ephemeral"}
            icerik_parcalari.extend(ref_bloklari)

    # Mevcut BRD ve revize içerik (değişken — cache'lenmiyor)
    icerik_parcalari.append({
        "type": "text",
        "text": f"### Mevcut BRD (Baseline)\n\n{mevcut_brd}",
    })
    icerik_parcalari.extend(revize_icerik)

    if ek_baglam:
        icerik_parcalari.append({
            "type": "text",
            "text": f"### Önceki BRD Analizi\n\n{ek_baglam}",
        })

    icerik_parcalari.append({
        "type": "text",
        "text": "İki BRD'yi karşılaştır, kapsam analizi ve alternatif süreçleri üret.",
    })

    rol = prompt_yukle("kapsam_analizi_rol")
    bolumler = prompt_yukle("kapsam_analizi_bolumler")
    alt_format = prompt_yukle("kapsam_analizi_alternatifler")

    sistem = (
        rol + "\n\n"
        "Yanıtını iki XML bloğu halinde ver:\n\n"
        f"<kapsam_analizi>\n{bolumler}\n</kapsam_analizi>\n\n"
        f"<alternatif_surecler>\n3-5 alternatif:\n{alt_format}\n</alternatif_surecler>"
    )

    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_KAPSAM)
    yanit = _metin_sikistir(yanit)

    kapsam     = _xml_ayir(yanit, "kapsam_analizi")
    alternatif = _xml_ayir(yanit, "alternatif_surecler")

    if kullanilan_referanslar:
        meta = "<!--\nKULLANILAN REFERANSLAR:\n- " + "\n- ".join(kullanilan_referanslar) + "\n-->\n\n"
        kapsam = meta + kapsam

    kapsam_yol     = _kaydet("kapsam-analizi.md", kapsam)
    alternatif_yol = _kaydet("alternatif-surecler.md", alternatif)

    return kapsam_yol, alternatif_yol
