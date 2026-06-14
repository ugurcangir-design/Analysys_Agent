"""Teknik analiz — İKİ AŞAMALI üretim.

Aşama 1: Teknik analiz (1-11. bölümler) → teknik-analiz.md
Aşama 2: Karar Bekleyen Konular / açık sorular AYRI çağrı → acik-sorular.md

İki ayrı, daha küçük API çağrısı: her biri tek dev çağrıdan hızlı biter,
timeout riskini düşürür. Teknik analiz biter bitmez kaydedilir; açık
sorular ondan sonra bağımsız adım olarak üretilir.
"""

import re
from pathlib import Path
from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    dosya_oku, referans_dosyalari_hazirla, _ref_bloklari_olustur, ui_kodu_hazirla,
    prompt_yukle, extended_thinking_acik,
    OUTPUT_DIR,
    MAX_CHARS_GENEL,
    MAX_TOKENS_COMBINED, MAX_TOKENS_UZUN,
)
from .html_mockup import mockup_oku_kontekst


def _teknik_prompt_olustur(ui_kodu: str | None, mockup_var: bool = False) -> str:
    """Aşama 1 sistem promptu — SADECE teknik analiz (açık sorular ayrı aşamada)."""
    rol = prompt_yukle("teknik_analiz_rol")
    bolumler = prompt_yukle("teknik_analiz_bolumler")
    # Güvenlik ağı: "Açık Sorular / Karar Bekleyen Konular" başlığı prompta
    # sızarsa Aşama 1'den ÇIKAR — bu bölüm AYRI çağrıda üretiliyor. Aksi halde
    # sorular iki kez üretilir ve Aşama 1 uzayıp timeout riskini geri getirir.
    bolumler = re.sub(
        r"(?ims)^#{1,3}\s*\d+\.\s*(?:Açık Sorular|Karar Bekleyen Konular).*?(?=^#{1,3}\s|\Z)",
        "",
        bolumler,
    ).strip()
    ekler = []
    if ui_kodu:
        ekler.append("Mevcut UI kaynak kodu da sağlanmıştır. Bölüm 7 (Frontend İş Kırılımı)'nda mevcut ekranları ve gerekli değişiklikleri/eklemeleri belirt.")
    if mockup_var:
        ekler.append("HTML prototip de sağlanmıştır. Bölüm 7 (Frontend İş Kırılımı)'nda prototipdeki ekranları, bileşenleri ve UX kararlarını teknik analize yansıt.")
    ek_metin = ("\n\n" + "\n".join(ekler)) if ekler else ""
    return (
        rol + ek_metin + "\n\n"
        "Teknik analiz raporunu TEK bir XML bloğu halinde ver. Açık sorular AYRI "
        "bir adımda üretilecek — burada açık soru bölümü YAZMA, yalnızca aşağıdaki "
        "bölümleri eksiksiz doldur:\n\n"
        f"<teknik_analiz>\n{bolumler}\n</teknik_analiz>"
    )


def _acik_sorular_prompt_olustur() -> str:
    """Aşama 2 sistem promptu — açık sorular (teknik analiz + süreç analizi girdi)."""
    sorular = prompt_yukle("teknik_analiz_sorular")
    return (
        "Kıdemli yazılım mimarı olarak, ürettiğin teknik analiz ve kaynak süreç "
        "analizini gözden geçir. Geliştirme ekibinin koda başlamadan ÖNCE "
        "netleştirmesi gereken TÜM belirsizlikleri, çelişkileri, eksik kararları "
        "ve kaynaksız varsayımları açık soru olarak topla.\n\n"
        "Kurallar:\n"
        "- Teknik analizde `[K: ❓ Belirsiz]` veya `⚠ VARSAYIM` işaretli her konu bir soru olmalı\n"
        "- Süreç analizinden gelen Q-XXX'lar teknik bağlamda hâlâ açıksa dahil et\n"
        "- Her soru BAĞIMSIZ cevaplanabilir ve tek konuya odaklı olmalı\n"
        "- Önem sırasına göre (Kritik → Yüksek → Orta → Düşük) sırala\n\n"
        "Çıktıyı TEK bir XML bloğu halinde ver:\n\n"
        f"<acik_sorular>\n{sorular}\n</acik_sorular>"
    )


def _acik_sorular_uret(teknik_metni: str, surec_metni: str) -> str:
    """Aşama 2 — teknik analizi girdi alıp açık soruları AYRI çağrıyla üretir."""
    print("  Açık sorular ayrı adımda üretiliyor...")
    sistem = _acik_sorular_prompt_olustur()
    icerik = [
        {"type": "text", "text": f"### Üretilen Teknik Analiz\n\n{teknik_metni}"},
        {"type": "text", "text": f"### Kaynak Süreç Analizi\n\n{surec_metni}"},
        {"type": "text", "text": "Yukarıdaki teknik analiz ve süreç analizindeki tüm açık konuları soru olarak topla."},
    ]
    mesajlar = [{"role": "user", "content": icerik}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_UZUN, thinking=extended_thinking_acik())
    yanit = _metin_sikistir(yanit)
    return _xml_ayir(yanit, "acik_sorular")


def teknik_analiz_yap() -> tuple[Path, Path]:
    print("Teknik analiz başlatılıyor...")
    surec_dosya = OUTPUT_DIR / "surec-analizi.md"
    if not surec_dosya.exists():
        raise FileNotFoundError("surec-analizi.md bulunamadı. Önce süreç analizi yapın.")

    surec_metni = dosya_oku(surec_dosya, MAX_CHARS_GENEL)
    ui_kodu = ui_kodu_hazirla()
    ref_dosyalar = referans_dosyalari_hazirla()
    mockup_icerik = mockup_oku_kontekst()

    icerik_parcalari: list[dict] = []
    kullanilan_referanslar: list[str] = []
    # Stable bloklar = değişmeyen içerik (referanslar + mockup + UI kodu)
    # Bunların sonuncusuna cache breakpoint eklenir → sonraki run'larda cache hit
    stable_bloklar: list[dict] = []

    if ref_dosyalar:
        print(f"  {len(ref_dosyalar)} referans dosya dahil ediliyor...")
        ref_bloklari, kullanilan_referanslar = _ref_bloklari_olustur(ref_dosyalar)
        stable_bloklar.extend(ref_bloklari)

    if mockup_icerik:
        print(f"  HTML prototip dahil ediliyor ({len(mockup_icerik):,} karakter)...")
        stable_bloklar.append({"type": "text", "text": f"### HTML Prototip\n\n{mockup_icerik}"})

    if ui_kodu:
        print(f"  UI kodu dahil ediliyor ({len(ui_kodu):,} karakter)...")
        stable_bloklar.append({"type": "text", "text": f"### Mevcut UI Kodu\n\n{ui_kodu}"})

    # Stable blokların sonuna cache breakpoint koy — sonraki run'larda cache hit
    if stable_bloklar:
        stable_bloklar[-1]["cache_control"] = {"type": "ephemeral"}
        icerik_parcalari.extend(stable_bloklar)

    icerik_parcalari.append({
        "type": "text",
        "text": (
            "### Süreç Analizi\n"
            "Aşağıdaki süreç analizindeki BR-XXX, AC-XXX, PA-XXX, EF-XXX, AF-XXX, EK-XXX "
            "ID'lerini teknik analizdeki ilgili bölümlerde (İş Gereksinimleri, API, "
            "Veritabanı, Kabul Kriterleri) MUTLAKA referans al — her teknik karar bir "
            "süreç ID'sini karşılamalı.\n\n"
            f"{surec_metni}"
        ),
    })
    icerik_parcalari.append({"type": "text", "text": "Teknik analiz raporunu üret (açık sorular HARİÇ — onlar ayrı adımda)."})

    # ── AŞAMA 1: Sadece teknik analiz ──
    sistem = _teknik_prompt_olustur(ui_kodu, mockup_var=bool(mockup_icerik))
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_COMBINED, thinking=extended_thinking_acik())
    yanit = _metin_sikistir(yanit)
    teknik = _xml_ayir(yanit, "teknik_analiz")

    if kullanilan_referanslar:
        meta = "<!--\nKULLANILAN REFERANSLAR:\n- " + "\n- ".join(kullanilan_referanslar) + "\n-->\n\n"
        teknik = meta + teknik

    # Teknik analiz BİTER BİTMEZ kaydet — açık sorular adımı başarısız olsa bile
    # teknik analiz korunur.
    teknik_yol = _kaydet("teknik-analiz.md", teknik)

    # ── AŞAMA 2: Açık sorular (ayrı çağrı) ──
    try:
        sorular = _acik_sorular_uret(teknik, surec_metni)
    except Exception as e:
        # Açık sorular üretimi başarısız olursa teknik analizi kaybetme;
        # açık sorular dosyasına hata notu yaz, akış devam etsin.
        print(f"  ⚠ Açık sorular üretilemedi: {e}")
        sorular = (
            "# Açık Sorular\n\n"
            "⚠ Açık sorular otomatik üretilemedi (teknik analiz başarıyla tamamlandı). "
            "Çıktılar sekmesinde 'Yeniden Çalıştır' ile açık soruları tekrar üretebilirsiniz.\n\n"
            f"Hata: {e}"
        )
    sorular_yol = _kaydet("acik-sorular.md", sorular)

    return teknik_yol, sorular_yol
