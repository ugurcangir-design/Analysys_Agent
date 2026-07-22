"""CR / Delta Analizi — mevcut teknik analiz + değişiklik isteği → yalnızca DELTA raporu.

Spec-driven araçların (Kiro, GitHub Spec Kit) 'spec evolves with change requests'
deseninin Analyst Studio karşılığı: test ortamına çıkmış bir özellik için gelen
CR/bug-fix talebi, sıfırdan tam analiz yerine mevcut analizin ÜZERİNE delta olarak
işlenir — daha az token, mevcut ID/bölüm şemasına bağlı izlenebilir çıktı.
"""

from pathlib import Path

from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    dosya_oku, prompt_yukle, belirsizlik_denetimi, ai_ara_sozleri_temizle,
    referans_dosyalari_hazirla, _ref_bloklari_olustur,
    canli_uygulama_baglami_hazirla,
    OUTPUT_DIR, MAX_CHARS_GENEL, MAX_TOKENS_UZUN,
    extended_thinking_acik,
)


def delta_analizi_yap(cr_metni: str) -> Path:
    """cr_metni: analistin girdiği değişiklik isteği / bug-fix tarifi (düz metin).
    Mevcut teknik-analiz.md ZORUNLU girdi; surec-analizi.md varsa bağlama eklenir.
    Çıktı: output/delta-analizi.md"""
    cr_metni = (cr_metni or "").strip()
    if not cr_metni:
        raise ValueError("Değişiklik isteği (CR) metni boş olamaz.")

    teknik_yol = OUTPUT_DIR / "teknik-analiz.md"
    if not teknik_yol.exists():
        raise FileNotFoundError(
            "teknik-analiz.md bulunamadı. Delta analizi mevcut bir teknik analizin "
            "üzerine çalışır — önce tam analiz üretin."
        )
    teknik_metni = dosya_oku(teknik_yol, MAX_CHARS_GENEL)

    print("Delta analizi başlatılıyor...")
    icerik_parcalari: list[dict] = []

    # Referanslar (bağlam filtresiyle) — CR çoğu zaman mevcut servis/ekran bilgisine dayanır
    ref_dosyalar = referans_dosyalari_hazirla()
    if ref_dosyalar:
        print(f"  {len(ref_dosyalar)} referans dosya dahil ediliyor...")
        ref_bloklari, _ = _ref_bloklari_olustur(ref_dosyalar)
        icerik_parcalari.extend(ref_bloklari)

    # Canlı uygulama gözlemi — CR'nin hedeflediği ekranın GÜNCEL hali için değerli
    canli_baglam = canli_uygulama_baglami_hazirla()
    if canli_baglam:
        print("  Canlı uygulama MCP/Chrome hedefleri dahil ediliyor...")
        icerik_parcalari.append({"type": "text", "text": canli_baglam})

    if icerik_parcalari:
        icerik_parcalari[-1]["cache_control"] = {"type": "ephemeral"}

    surec_yol = OUTPUT_DIR / "surec-analizi.md"
    if surec_yol.exists():
        icerik_parcalari.append({
            "type": "text",
            "text": "### Mevcut Süreç Analizi (bağlam)\n\n" + dosya_oku(surec_yol, MAX_CHARS_GENEL),
        })

    icerik_parcalari.append({
        "type": "text",
        "text": "### Mevcut Teknik Analiz (delta bunun üzerine işlenecek)\n\n" + teknik_metni,
    })
    icerik_parcalari.append({
        "type": "text",
        "text": "### Değişiklik İsteği (CR / bug-fix)\n\n" + cr_metni,
    })
    icerik_parcalari.append({
        "type": "text",
        "text": "Değişiklik isteğini mevcut teknik analizle karşılaştır ve delta analizi raporunu üret.",
    })

    sistem = prompt_yukle("delta_analizi")
    yanit = _api_cagri(sistem, [{"role": "user", "content": icerik_parcalari}],
                       max_tokens=MAX_TOKENS_UZUN, thinking=extended_thinking_acik(),
                       canli_uygulama_kapsami=("surec" if canli_baglam else None))
    # AI'ın süreç anlatımı ara sözlerini ("Şimdi raporu yazıyorum." vb.) çıkar.
    delta = ai_ara_sozleri_temizle(_xml_ayir(_metin_sikistir(yanit), "delta_analizi"))

    belirsizlik = belirsizlik_denetimi(delta)
    if belirsizlik:
        print("  🔎 Belirsizlik denetimi: muğlak ifadeler bulundu — rapora eklendi.")
    return _kaydet("delta-analizi.md", delta + belirsizlik)
