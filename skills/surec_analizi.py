"""Süreç analizi — input dosyasını okur, analiz raporu üretir."""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet, input_hazirla, prompt_yukle,
    MAX_TOKENS_UZUN,
)


def surec_analizi_yap() -> Path:
    print("Süreç analizi başlatılıyor...")
    icerik, dosya_adi = input_hazirla(is_brd=False)
    print(f"  Dosya: {dosya_adi}")
    sistem = prompt_yukle("surec_analizi")
    mesajlar = [{"role": "user", "content": icerik + [
        {"type": "text", "text": "Yukarıdaki dokümanı analiz et ve süreç analizi raporunu üret."}
    ]}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_UZUN)
    return _kaydet("surec-analizi.md", yanit)
