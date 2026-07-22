"""Süreç analizi — input dosyasını + referansları okur, analiz raporu üretir."""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet, input_hazirla, prompt_yukle, ozel_prompt_oku,
    OZEL_PROMPT_DOGRULUK_EKI, belirsizlik_denetimi, ai_ara_sozleri_temizle,
    referans_dosyalari_hazirla, _ref_bloklari_olustur,
    canli_uygulama_baglami_hazirla,
    yonetici_ozeti_olustur,
    MAX_TOKENS_UZUN,
    extended_thinking_acik,
)


def _surec_prompt_olustur() -> str:
    # Analistin ekrandan girdiği özel prompt VARSA varsayılanın YERİNE geçer
    # (rol + bölümler tamamen atlanır). Boşsa mevcut davranış aynen korunur.
    # Doğruluk çekirdeği (kaynak kullanımı + uydurmama + [K:] etiketi) özel
    # prompta da EKLENİR — bunlar analistin vazgeçebileceği kurallar değil.
    ozel = ozel_prompt_oku("surec")
    if ozel:
        print("  ✏️ Özel süreç analizi promptu kullanılıyor (varsayılan atlandı).")
        return ozel + OZEL_PROMPT_DOGRULUK_EKI
    rol = prompt_yukle("surec_analizi_rol")
    bolumler = prompt_yukle("surec_analizi")
    # Mermaid akış diyagramı — Süreç Adımları bölümüne görsel özet (ChatPRD/Keeborg
    # benzeri). Kısa tutulur; çıktı görüntüleyici mermaid bloklarını render eder.
    mermaid_talimati = (
        "\n\nEK: Süreç Adımları bölümünün SONUNA ana akışı özetleyen bir mermaid akış "
        "diyagramı ekle (```mermaid çitli blok, `flowchart TD`). Yalnızca ana adımlar + "
        "kritik karar noktaları (en fazla ~12 düğüm); alternatif akışları tek düğümle işaret et. "
        "Düğüm etiketlerinde PA-XXX ID'lerini kullan."
    )
    return rol + "\n\n## ÇIKTI BÖLÜMLERİ\n\n" + bolumler + mermaid_talimati


def surec_analizi_yap() -> Path:
    print("Süreç analizi başlatılıyor...")
    icerik, dosya_adi = input_hazirla(is_brd=False)
    print(f"  Dosya: {dosya_adi}")

    icerik_parcalari: list[dict] = []
    kullanilan_referanslar: list[str] = []

    # Tüm referans kaynaklarını (Confluence, Jira, Swagger, canlı uygulama, diğer) tipine göre gruplandır
    ref_dosyalar = referans_dosyalari_hazirla()
    if ref_dosyalar:
        print(f"  {len(ref_dosyalar)} referans dosya dahil ediliyor...")
        ref_bloklari, kullanilan_referanslar = _ref_bloklari_olustur(ref_dosyalar)
        if ref_bloklari:
            icerik_parcalari.extend(ref_bloklari)

    canli_baglam = canli_uygulama_baglami_hazirla()
    if canli_baglam:
        print("  Canlı uygulama MCP/Chrome hedefleri dahil ediliyor...")
        icerik_parcalari.append({"type": "text", "text": canli_baglam})

    if icerik_parcalari:
        # Son stabil bloğa cache breakpoint — rerun ve takip eden analizlerde cache hit
        icerik_parcalari[-1]["cache_control"] = {"type": "ephemeral"}

    icerik_parcalari.extend(icerik)
    icerik_parcalari.append({
        "type": "text",
        "text": "Yukarıdaki ana dokümanı (varsa referanslarla birlikte) analiz et ve süreç analizi raporunu üret.",
    })

    sistem = _surec_prompt_olustur()
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_UZUN, thinking=extended_thinking_acik(),
                       canli_uygulama_kapsami=("surec" if canli_baglam else None))
    # AI'ın süreç anlatımı ara sözlerini ("Şimdi raporu yazıyorum." vb.) çıkar.
    yanit = ai_ara_sozleri_temizle(yanit)

    if kullanilan_referanslar:
        meta = "<!--\nKULLANILAN REFERANSLAR:\n- " + "\n- ".join(kullanilan_referanslar) + "\n-->\n\n"
        yanit = meta + yanit

    # Belirsizlik Denetimi — deterministik, 0 token: muğlak ifadeler raporu sona eklenir.
    belirsizlik = belirsizlik_denetimi(yanit)
    if belirsizlik:
        print("  🔎 Belirsizlik denetimi: muğlak ifadeler bulundu — rapora eklendi.")

    # Yönetici Özeti (TL;DR) — analist hızlı tarayıp onaylasın. Süreç analizi Jira'ya
    # gitmez ama tutarlılık için aynı format (açık sorular doküman içinde, tablo formatı).
    ozet = yonetici_ozeti_olustur(yanit)
    return _kaydet("surec-analizi.md", ozet + yanit + belirsizlik)
