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
    prompt_yukle, extended_thinking_acik, surec_id_kapsam,
    OUTPUT_DIR,
    MAX_CHARS_GENEL,
    MAX_TOKENS_COMBINED, MAX_TOKENS_UZUN, MAX_TOKENS_KAPSAM,
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


def _teknik_uret_tam(sistem: str, mesajlar: list, max_deneme: int = 2) -> str:
    """Aşama 1 üretimi — kapanış </teknik_analiz> etiketi yoksa çıktı KESİLMİŞ
    demektir (özellikle CLI modu uzun analizde bazen erken biter; max_tokens CLI'de
    geçerli değil). Tam yanıt gelene kadar (en fazla max_deneme) yeniden dener;
    hiçbiri tam değilse en dolu ham yanıtı döndürür (_xml_ayir yarımı yine ayıklar).
    Böylece eksik teknik analiz SESSİZCE kaydedilmez."""
    en_dolu = ""
    for deneme in range(1, max_deneme + 1):
        ham = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_COMBINED, thinking=extended_thinking_acik())
        if "</teknik_analiz>" in ham:
            if deneme > 1:
                print(f"  ✓ {deneme}. denemede tam teknik analiz üretildi")
            return ham
        if len(ham) > len(en_dolu):
            en_dolu = ham
        if deneme < max_deneme:
            print(f"  ⚠ Teknik analiz kesik geldi (kapanış etiketi yok) — yeniden deneniyor ({deneme}/{max_deneme})...")
    print("  ⛔ Teknik analiz tam üretilemedi — eldeki en dolu çıktı kaydedilecek (eksik olabilir).")
    return en_dolu


def _acik_sorular_uret(teknik_metni: str, surec_metni: str, eksik_idler: list[str] | None = None) -> str:
    """Aşama 2 — teknik analizi girdi alıp açık soruları AYRI çağrıyla üretir.
    eksik_idler verilirse (kapsam denetiminden), teknik analizde referans
    bulunamayan süreç ID'leri açık soru olarak garantili eklenir."""
    print("  Açık sorular ayrı adımda üretiliyor...")
    sistem = _acik_sorular_prompt_olustur()
    icerik = [
        {"type": "text", "text": f"### Üretilen Teknik Analiz\n\n{teknik_metni}"},
        {"type": "text", "text": f"### Kaynak Süreç Analizi\n\n{surec_metni}"},
    ]
    if eksik_idler:
        icerik.append({"type": "text", "text": (
            "### Otomatik Kapsam Denetimi — Karşılanmayan Süreç ID'leri\n"
            "Aşağıdaki süreç gereksinim ID'leri teknik analizde referans BULUNAMADI. "
            "Her biri için, teknik analizde neden ele alınmadığını netleştiren bir açık "
            "soru ekle (sorunun 'Bağlı ID' alanına ilgili ID'yi yaz):\n"
            + ", ".join(eksik_idler)
        )})
    icerik.append({"type": "text", "text": "Yukarıdaki teknik analiz ve süreç analizindeki tüm açık konuları soru olarak topla."})
    mesajlar = [{"role": "user", "content": icerik}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_UZUN, thinking=extended_thinking_acik())
    yanit = _metin_sikistir(yanit)
    return _xml_ayir(yanit, "acik_sorular")


def _teknik_denetci_prompt_olustur() -> str:
    """Denetçi (Aşama 3) sistem promptu."""
    return prompt_yukle("teknik_analiz_denetci")


def _teknik_denetle(teknik_metni: str, surec_metni: str) -> str:
    """Aşama 3 — üretilen teknik analizi kalite/tutarlılık açısından denetler.
    Yeni içerik üretmez; kaynaksız iddia, §5↔§7 validasyon drift'i, uydurma
    endpoint/tablo, hata tutarsızlığı vb. bulgularını döndürür."""
    print("  Otomatik denetçi çalışıyor (kaynaksız iddia / tutarsızlık taraması)...")
    sistem = _teknik_denetci_prompt_olustur()
    icerik = [
        {"type": "text", "text": f"### Denetlenecek Teknik Analiz\n\n{teknik_metni}"},
        {"type": "text", "text": f"### Kaynak Süreç Analizi\n\n{surec_metni}"},
        {"type": "text", "text": "Yukarıdaki teknik analizi kontrol listesine göre denetle ve bulguları üret."},
    ]
    mesajlar = [{"role": "user", "content": icerik}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_KAPSAM, thinking=False)
    yanit = _metin_sikistir(yanit)
    return _xml_ayir(yanit, "denetim_notlari")


def _denetim_bolumu_olustur(kapsam: dict, denetim_notlari: str) -> str:
    """Kapsam özeti + denetçi bulgularını teknik analize eklenecek bölüm olarak biçimler."""
    eksik_str = ", ".join(kapsam["eksik"]) if kapsam["eksik"] else "yok"
    return (
        "\n\n---\n\n"
        "## 🔍 Otomatik Denetim Notları\n\n"
        "_Bu bölüm otomatik üretildi (deterministik kapsam denetimi + AI denetçi). "
        "Asıl teknik analiz yukarıdadır; aşağıdakiler gözden geçirme notlarıdır._\n\n"
        f"**Süreç gereksinim kapsamı:** {len(kapsam['karsilanan'])}/{kapsam['toplam']} "
        f"ID karşılandı (%{kapsam['skor']*100:.0f}). Karşılanmayan: {eksik_str}\n\n"
        f"{denetim_notlari}\n"
    )


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
    yanit = _teknik_uret_tam(sistem, mesajlar)
    yanit = _metin_sikistir(yanit)
    teknik = _xml_ayir(yanit, "teknik_analiz")

    if kullanilan_referanslar:
        meta = "<!--\nKULLANILAN REFERANSLAR:\n- " + "\n- ".join(kullanilan_referanslar) + "\n-->\n\n"
        teknik = meta + teknik

    # Teknik analiz BİTER BİTMEZ kaydet — sonraki adımlar başarısız olsa bile
    # ham teknik analiz korunur.
    teknik_ham = teknik
    teknik_yol = _kaydet("teknik-analiz.md", teknik_ham)

    # ── Kapsam denetimi (deterministik): süreç ID'leri karşılandı mı? ──
    kapsam = surec_id_kapsam(surec_metni, teknik_ham)
    print(f"  İzlenebilirlik: {len(kapsam['karsilanan'])}/{kapsam['toplam']} süreç ID karşılandı (%{kapsam['skor']*100:.0f})")
    if kapsam["eksik"]:
        print(f"  ⚠ Karşılanmayan süreç ID'leri: {', '.join(kapsam['eksik'])}")

    # ── AŞAMA 3: Otomatik denetçi (AI) — ham teknik analize denetim bölümü ekle ──
    try:
        denetim_notlari = _teknik_denetle(teknik_ham, surec_metni)
        teknik_yol = _kaydet("teknik-analiz.md", teknik_ham + _denetim_bolumu_olustur(kapsam, denetim_notlari))
    except Exception as e:
        # Denetçi başarısız olsa bile ham teknik analiz zaten kayıtlı.
        print(f"  ⚠ Otomatik denetçi çalışmadı (ham teknik analiz korundu): {e}")

    # ── AŞAMA 2: Açık sorular (ayrı çağrı; karşılanmayan ID'ler garantili eklenir) ──
    try:
        sorular = _acik_sorular_uret(teknik_ham, surec_metni, kapsam["eksik"])
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
