"""BRD analizi + sorular — tek API çağrısında XML combined output."""

import shutil
from pathlib import Path
from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    input_hazirla, prompt_yukle, extended_thinking_acik,
    INPUT_DIR, REF_DIR,
    MAX_TOKENS_BRD_CMB,
)

_BRD_BOLUMLER = """## 1. BRD Özeti
## 2. Fonksiyonel Gereksinimler
## 3. Fonksiyonel Olmayan Gereksinimler
## 4. Paydaşlar ve Kullanıcı Hikayeleri
## 5. Kabul Kriterleri
## 6. Bağımlılıklar ve Kısıtlar
## 7. Kapsam Dışı
## 8. Eksiklikler ve Tutarsızlıklar"""

_BRD_SORULAR_FORMAT = """### S[N]: [Başlık]
- **Bölüm:** BRD bölüm adı
- **Öncelik:** Kritik/Yüksek/Orta
- **Soru:** ...
- **Mevcut Durum:** ...
- **Beklenen Yanıt:** ..."""

_BRD_ANALIZ_COMBINED_SISTEM = (
    "Kıdemli ürün ve iş analisti olarak BRD dokümanını TAMAMIYLA analiz et (çok sayfalı olsa bile tüm bölümleri oku).\n\n"
    "Yanıtını iki XML bloğu halinde ver:\n\n"
    "<brd_analizi>\n{bolumler}\n</brd_analizi>\n\n"
    "<brd_sorular>\nProduct Owner için en önemli 12 soru:\n{soru_format}\n</brd_sorular>"
)


def brd_analizi_yap() -> tuple[Path, Path]:
    print("BRD analizi başlatılıyor...")
    icerik, dosya_adi = input_hazirla(is_brd=True)
    print(f"  Dosya: {dosya_adi}")

    sistem = _BRD_ANALIZ_COMBINED_SISTEM.format(
        bolumler=prompt_yukle("brd_analizi_bolumler"),
        soru_format=_BRD_SORULAR_FORMAT,
    )
    mesajlar = [{"role": "user", "content": icerik + [
        {"type": "text", "text": "BRD dokümanını analiz et ve soruları üret."}
    ]}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_BRD_CMB, thinking=extended_thinking_acik())
    yanit = _metin_sikistir(yanit)

    analiz  = _xml_ayir(yanit, "brd_analizi")
    sorular = _xml_ayir(yanit, "brd_sorular")

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
