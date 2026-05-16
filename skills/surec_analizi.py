"""Süreç analizi — input dosyasını + referansları okur, analiz raporu üretir."""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet, input_hazirla, prompt_yukle,
    dosya_oku, referans_dosyalari_hazirla,
    OUTPUT_DIR, REF_DIR,
    MAX_TOKENS_UZUN, MAX_CHARS_REF, MAX_CHARS_REF_TOT,
    extended_thinking_acik,
)


def _surec_prompt_olustur() -> str:
    rol = prompt_yukle("surec_analizi_rol")
    bolumler = prompt_yukle("surec_analizi")
    return rol + "\n\n## ÇIKTI BÖLÜMLERİ\n\n" + bolumler


def surec_analizi_yap() -> Path:
    print("Süreç analizi başlatılıyor...")
    icerik, dosya_adi = input_hazirla(is_brd=False)
    print(f"  Dosya: {dosya_adi}")

    icerik_parcalari = []
    kullanilan_referanslar: list[str] = []

    ref_dosyalar = referans_dosyalari_hazirla()
    if ref_dosyalar:
        print(f"  {len(ref_dosyalar)} referans dosya dahil ediliyor...")
        ref_metinler = []
        toplam_ref = 0
        for f in ref_dosyalar:
            try:
                rel = str(f.relative_to(REF_DIR))
            except ValueError:
                rel = f.name
            if toplam_ref >= MAX_CHARS_REF_TOT:
                try:
                    metin = dosya_oku(f, 800)
                except Exception:
                    continue
                ref_metinler.append(f"#### {rel} (özet)\n{metin}")
                kullanilan_referanslar.append(f"{rel} [özet]")
                continue
            try:
                metin = dosya_oku(f, MAX_CHARS_REF)
            except Exception:
                continue
            ref_metinler.append(f"#### {rel}\n{metin}")
            kullanilan_referanslar.append(rel)
            toplam_ref += len(metin)
        if ref_metinler:
            icerik_parcalari.append({
                "type": "text",
                "text": (
                    "### REFERANS DOKÜMANLAR\n"
                    "Bu süreç ile ilgili mevcut sistem dokümantasyonu, API tanımları ve önceki kararlar. "
                    "Süreç adımlarında bu kaynakları KULLAN ve `[K: <kaynak>]` ile işaretle.\n\n"
                    + "\n\n---\n\n".join(ref_metinler)
                ),
            })

    icerik_parcalari.extend(icerik)
    icerik_parcalari.append({
        "type": "text",
        "text": "Yukarıdaki ana dokümanı (varsa referanslarla birlikte) analiz et ve süreç analizi raporunu üret.",
    })

    sistem = _surec_prompt_olustur()
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_UZUN, thinking=extended_thinking_acik())

    if kullanilan_referanslar:
        meta = "<!--\nKULLANILAN REFERANSLAR:\n- " + "\n- ".join(kullanilan_referanslar) + "\n-->\n\n"
        yanit = meta + yanit

    return _kaydet("surec-analizi.md", yanit)
