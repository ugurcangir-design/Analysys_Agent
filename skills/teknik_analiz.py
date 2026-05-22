"""Teknik analiz + açık sorular — tek API çağrısında XML combined output."""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    dosya_oku, referans_dosyalari_hazirla, _ref_bloklari_olustur, ui_kodu_hazirla,
    prompt_yukle, extended_thinking_acik,
    OUTPUT_DIR,
    MODEL_ANALIZ, MAX_CHARS_GENEL,
    MAX_TOKENS_COMBINED,
)
from .html_mockup import mockup_oku_kontekst

_TEKNIK_UI_BOLUM = """

## 16. Yeni/Değişen Ekranlar (UI)
| Ekran / Route | Dosya | Tip | Bağlı PA-ID | Bileşenler | Yeni API'ler | Kaynak |
|---------------|-------|-----|-------------|------------|--------------|--------|
| /ornek | components/Ornek.tsx | Yeni/Güncelleme/Silme | PA-001 | OrnekForm, OrnekListe | POST /api/v1/ornek | [UI:routes] |

- UX kararları (mockup'tan): ...
- Form validation kuralları (Bölüm 5 ile aynı BR-ID'leri kullan)
- Hata mesajlarının ekranda nereye gösterileceği"""

def _teknik_prompt_olustur(ui_kodu: str | None, mockup_var: bool = False) -> str:
    rol = prompt_yukle("teknik_analiz_rol")
    bolumler = prompt_yukle("teknik_analiz_bolumler") + (_TEKNIK_UI_BOLUM if ui_kodu else "")
    sorular = prompt_yukle("teknik_analiz_sorular")
    ekler = []
    if ui_kodu:
        ekler.append("Mevcut UI kaynak kodu da sağlanmıştır. Bölüm 12'de mevcut ekranları ve gerekli değişiklikleri/eklemeleri belirt.")
    if mockup_var:
        ekler.append("HTML prototip de sağlanmıştır. Bölüm 12'de prototipdeki ekranları, bileşenleri ve UX kararlarını teknik analize yansıt.")
    ek_metin = ("\n\n" + "\n".join(ekler)) if ekler else ""
    return (
        rol + ek_metin + "\n\n"
        "Yanıtını iki XML bloğu halinde ver:\n\n"
        f"<teknik_analiz>\n{bolumler}\n</teknik_analiz>\n\n"
        f"<acik_sorular>\n{sorular}\n</acik_sorular>"
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
            "Aşağıdaki süreç analizindeki BR-XXX, AC-XXX, PA-XXX, EF-XXX, AF-XXX ID'lerini "
            "teknik analizdeki ilgili bölümlerde MUTLAKA referans al ve "
            "İzlenebilirlik Matrisi'nde göster.\n\n"
            f"{surec_metni}"
        ),
    })
    icerik_parcalari.append({"type": "text", "text": "Teknik analiz raporunu ve açık soruları üret."})

    sistem = _teknik_prompt_olustur(ui_kodu, mockup_var=bool(mockup_icerik))
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_COMBINED, thinking=extended_thinking_acik())
    yanit = _metin_sikistir(yanit)

    teknik  = _xml_ayir(yanit, "teknik_analiz")
    sorular = _xml_ayir(yanit, "acik_sorular")

    if kullanilan_referanslar:
        meta = "<!--\nKULLANILAN REFERANSLAR:\n- " + "\n- ".join(kullanilan_referanslar) + "\n-->\n\n"
        teknik = meta + teknik

    teknik_yol  = _kaydet("teknik-analiz.md", teknik)
    sorular_yol = _kaydet("acik-sorular.md", sorular)

    return teknik_yol, sorular_yol
