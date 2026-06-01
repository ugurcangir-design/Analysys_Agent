"""
HTML Prototip Skill — Adım 8.
Süreç analizinden çalışan HTML+CSS+JS prototipi üretir.
UI kodu yüklüyse mevcut tasarım diline uyar.
"""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet,
    dosya_oku, ui_kodu_hazirla, prompt_yukle,
    OUTPUT_DIR, MAX_CHARS_GENEL,
)

MAX_TOKENS_MOCKUP  = 8_000
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

_UI_HINT_GÖMÜLÜ = """\

Önemli: Mevcut UI kaynak kodu sağlanmıştır. Aşağıdaki kurallara uy:
- Aynı renk paletini, tipografiyi ve spacing'i kullan
- Mevcut bileşen stillerini (buton, kart, form, tablo) taklit et
- Yeni ekranlar var olan sayfalarla görsel tutarlılık taşısın"""

_UI_HINT_YOK = """\

Tasarım rehberi: koyu sidebar + açık içerik alanı; accent rengi #5b5ef4; \
font-family: system-ui; temiz ve minimal."""


def mockup_hazirla_kontekst(ui_kodu_ozet: str | None) -> str:
    """
    ui-code/ içeriğinden kısa tasarım özeti çıkar.
    Tüm kodu geçmek yerine sadece CSS değişkenleri + ilk bileşen örnekleri alınır.
    """
    if not ui_kodu_ozet:
        return ""
    # CSS değişkenlerini ve ilk 3k karakteri al — tasarım dilini anlamak yeterli
    satirlar = []
    karakter = 0
    for satir in ui_kodu_ozet.splitlines():
        satirlar.append(satir)
        karakter += len(satir)
        if karakter >= 3_000:
            satirlar.append("... (kısaltıldı)")
            break
    return "\n".join(satirlar)


def html_mockup_uret() -> Path:
    """
    output/surec-analizi.md → output/mockup.html
    reference/ui-code/ varsa mevcut UI tasarımına uyar.
    """
    surec_dosya = OUTPUT_DIR / "surec-analizi.md"
    if not surec_dosya.exists():
        raise FileNotFoundError("surec-analizi.md bulunamadı. Önce süreç analizi yapın.")

    surec_metni = dosya_oku(surec_dosya, MAX_CHARS_GENEL)
    ui_kodu = ui_kodu_hazirla()

    if ui_kodu:
        print("  UI kodu mevcut — tasarım diline uygun prototip üretiliyor...")
        ui_ozet = mockup_hazirla_kontekst(ui_kodu)
        ui_hint = _UI_HINT_GÖMÜLÜ
        icerik_parcalari = [
            {"type": "text", "text": f"### Mevcut UI Kaynak Kodu (Tasarım Referansı)\n\n{ui_ozet}"},
            {"type": "text", "text": f"### Süreç Analizi\n\n{surec_metni}"},
            {"type": "text", "text": "Mevcut UI tasarım diline uygun HTML prototipi oluştur."},
        ]
    else:
        ui_hint = _UI_HINT_YOK
        icerik_parcalari = [
            {"type": "text", "text": f"### Süreç Analizi\n\n{surec_metni}"},
            {"type": "text", "text": "Bu süreç için HTML prototipi oluştur."},
        ]

    sistem = (prompt_yukle("html_mockup_base") + "\n{ui_hint}\nYalnızca HTML içeriğini ver — başka açıklama ekleme, kod bloğu (```) işareti kullanma.").format(ui_hint=ui_hint)
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_MOCKUP)

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
