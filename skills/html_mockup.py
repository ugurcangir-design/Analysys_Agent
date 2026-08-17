"""
HTML Prototip Skill — Adım 8.
Süreç analizinden çalışan HTML+CSS+JS prototipi üretir.
"""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet,
    dosya_oku, prompt_yukle,
    OUTPUT_DIR, MAX_CHARS_GENEL,
    canli_uygulama_baglami_hazirla,
)

MAX_TOKENS_MOCKUP  = 12_000   # CLI modunda etkisiz; API modu için canlı gözlem + üretim payı
MAX_CHARS_MOCKUP   = 20_000   # teknik analize dahil ederken uygulanan limit

_MOCKUP_SISTEM_BASE = """\
Deneyimli UI/UX tasarımcısı ve frontend geliştirici olarak süreç analizi dokümanından \
çalışan bir HTML prototipi oluştur.

Gereksinimler:
- Tek HTML dosyası (CSS ve JS gömülü); dış CDN kullanabilirsin
- Süreç analizindeki tüm ana ekranlar/adımlar gezinilebilir olmalı
- Gerçekçi form alanları, butonlar ve örnek veri gösterimi
- Sidebar veya tab ile ekranlar arası geçiş
- Türkçe UI metinleri, profesyonel görünüm
- Tıklanabilir butonlar çalışsın; formlar submit'te sonuç göstersin
{ui_hint}
Yalnızca HTML içeriğini ver — başka açıklama ekleme, kod bloğu (```) işareti kullanma."""

_UI_HINT_YOK = """\

Tasarım rehberi: koyu sidebar + açık içerik alanı; accent rengi #5b5ef4; \
font-family: system-ui; temiz ve minimal."""


def html_mockup_uret() -> Path:
    """
    output/surec-analizi.md → output/mockup.html
    """
    surec_dosya = OUTPUT_DIR / "surec-analizi.md"
    if not surec_dosya.exists():
        raise FileNotFoundError("surec-analizi.md bulunamadı. Önce süreç analizi yapın.")

    surec_metni = dosya_oku(surec_dosya, MAX_CHARS_GENEL)
    icerik_parcalari = [
        {"type": "text", "text": f"### Süreç Analizi\n\n{surec_metni}"},
    ]

    # Canlı uygulama (context_filter live_app: target_url + extra_urls) → Chrome MCP
    # gezinme görevi. URL tanımlıysa prototip, GÖZLEMLENEN ekranın tasarım dilini ve
    # component'lerini BAZ alır; değilse generic tasarım ipucuna düşer (fallback).
    kapsam = None
    gorev_talimati = canli_uygulama_baglami_hazirla()
    if gorev_talimati:
        icerik_parcalari.append({"type": "text", "text": gorev_talimati})
        kapsam = "surec"   # _api_cagri CLI modunda Chrome MCP'yi bu bayrakla açar
    ui_hint = "" if gorev_talimati else _UI_HINT_YOK

    icerik_parcalari.append(
        {"type": "text",
         "text": "Bu süreç ve (görev verildiyse) gözlemlenen canlı ekranı baz alarak, "
                 "tüm component'leri çalışan HTML prototipi oluştur."})

    sistem = (prompt_yukle("html_mockup_base") + "\n" + ui_hint +
              "\nYalnızca HTML içeriğini ver — başka açıklama ekleme, kod bloğu (```) işareti kullanma.")
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_MOCKUP,
                       canli_uygulama_kapsami=kapsam)

    # AI bazen ```html ... ``` bloğu içinde döndürür — sadece içeriği al
    yanit = yanit.strip()
    if yanit.startswith("```"):
        satirlar = yanit.splitlines()
        yanit = "\n".join(satirlar[1:])
        if yanit.rstrip().endswith("```"):
            yanit = yanit.rstrip()[:-3].rstrip()

    return _kaydet("mockup.html", yanit)


def mockup_oku_kontekst() -> str | None:
    """
    output/mockup.html varsa teknik analize dahil edilecek kısa özet döndür.
    Tüm HTML yerine body içeriği + style özeti — token tasarrufu için.
    """
    mockup_dosya = OUTPUT_DIR / "mockup.html"
    if not mockup_dosya.exists():
        return None

    icerik = mockup_dosya.read_text(encoding="utf-8", errors="replace")
    if len(icerik) <= MAX_CHARS_MOCKUP:
        return icerik

    # Büyük prototiplerde: <body> içeriğini + <style> başını al
    import re
    body_m  = re.search(r'<body[^>]*>(.*?)</body>', icerik, re.DOTALL | re.IGNORECASE)
    style_m = re.search(r'<style[^>]*>(.*?)</style>', icerik, re.DOTALL | re.IGNORECASE)

    parcalar = []
    if style_m:
        style_ozet = style_m.group(1)[:2_000]
        parcalar.append(f"<style>\n{style_ozet}\n/* ... kısaltıldı ... */\n</style>")
    if body_m:
        body_ozet = body_m.group(1)[:MAX_CHARS_MOCKUP - len(parcalar[0]) if parcalar else MAX_CHARS_MOCKUP]
        parcalar.append(f"<body>\n{body_ozet}\n<!-- ... kısaltıldı ... -->\n</body>")

    return "\n".join(parcalar) if parcalar else icerik[:MAX_CHARS_MOCKUP]
