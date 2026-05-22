"""BRD analizi + sorular — tek API çağrısında XML combined output."""

import shutil
from pathlib import Path
from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    input_hazirla, referans_dosyalari_hazirla, _ref_bloklari_olustur,
    prompt_yukle, extended_thinking_acik,
    INPUT_DIR, REF_DIR,
    MAX_TOKENS_BRD_CMB,
)


def brd_analizi_yap() -> tuple[Path, Path]:
    print("BRD analizi başlatılıyor...")
    icerik, dosya_adi = input_hazirla(is_brd=True)
    print(f"  Dosya: {dosya_adi}")

    icerik_parcalari: list[dict] = []
    kullanilan_referanslar: list[str] = []

    # Tüm referans kaynaklarını (Confluence, Jira, Swagger, diğer) tipine göre gruplandır.
    # BRD analizi için referanslar: mevcut sistem durumunu anlamak ve
    # BRD ile çelişen/destekleyen kanıtları bulmak için kullanılır.
    ref_dosyalar = referans_dosyalari_hazirla()
    if ref_dosyalar:
        print(f"  {len(ref_dosyalar)} referans dosya dahil ediliyor...")
        ref_bloklari, kullanilan_referanslar = _ref_bloklari_olustur(ref_dosyalar)
        if ref_bloklari:
            # Son referans bloğuna cache breakpoint — aynı BRD için birden fazla analiz yapılırsa cache hit
            ref_bloklari[-1]["cache_control"] = {"type": "ephemeral"}
            icerik_parcalari.extend(ref_bloklari)

    # BRD dokümanı (değişken içerik — cache'lenmiyor)
    icerik_parcalari.extend(icerik)
    icerik_parcalari.append({
        "type": "text",
        "text": "BRD dokümanını analiz et. Varsa referanslarla çapraz kontrol yap, çelişkileri raporla.",
    })

    rol = prompt_yukle("brd_analizi_rol")
    bolumler = prompt_yukle("brd_analizi_bolumler")
    sorular_fmt = prompt_yukle("brd_analizi_sorular")
    sistem = (
        rol + "\n\n"
        "Yanıtını iki XML bloğu halinde ver:\n\n"
        f"<brd_analizi>\n{bolumler}\n</brd_analizi>\n\n"
        f"<brd_sorular>\nProduct Owner için en önemli 12 soru:\n{sorular_fmt}\n</brd_sorular>"
    )
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_BRD_CMB, thinking=extended_thinking_acik())
    yanit = _metin_sikistir(yanit)

    analiz  = _xml_ayir(yanit, "brd_analizi")
    sorular = _xml_ayir(yanit, "brd_sorular")

    if kullanilan_referanslar:
        meta = "<!--\nKULLANILAN REFERANSLAR:\n- " + "\n- ".join(kullanilan_referanslar) + "\n-->\n\n"
        analiz = meta + analiz

    analiz_yol  = _kaydet("brd-analizi.md", analiz)
    sorular_yol = _kaydet("brd-sorular.md", sorular)

    return analiz_yol, sorular_yol


def brd_final_kaydet() -> Path:
    """Revize BRD'yi reference/current-brd/ klasörüne kopyala."""
    dosyalar = sorted(
        f for f in INPUT_DIR.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    if not dosyalar:
        raise FileNotFoundError("input/ klasöründe dosya yok.")

    brd_dir = REF_DIR / "current-brd"
    brd_dir.mkdir(parents=True, exist_ok=True)

    for eski in brd_dir.iterdir():
        if eski.is_file():
            eski.unlink()

    dosya = dosyalar[0]
    hedef = brd_dir / dosya.name
    shutil.copy2(dosya, hedef)
    print(f"✓ Final BRD kaydedildi: {hedef}")
    return hedef
