"""Teknik analiz + açık sorular — tek API çağrısında XML combined output."""

from pathlib import Path
from .base import (
    _api_cagri, _kaydet, _xml_ayir, _metin_sikistir,
    dosya_oku, referans_dosyalari_hazirla, ui_kodu_hazirla,
    prompt_yukle, extended_thinking_acik,
    OUTPUT_DIR, REF_DIR,
    MODEL_ANALIZ, MAX_CHARS_GENEL, MAX_CHARS_REF, MAX_CHARS_REF_TOT,
    MAX_TOKENS_COMBINED,
)
from .html_mockup import mockup_oku_kontekst

_TEKNIK_UI_BOLUM = """
## 12. Yeni/Değişen Ekranlar
Her ekran için: dosya/route adı, değişiklik türü (yeni/güncelleme/silme), etkilenen bileşenler."""

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

    icerik_parcalari = []

    if ref_dosyalar:
        print(f"  {len(ref_dosyalar)} referans dosya dahil ediliyor...")
        ref_metinler = []
        toplam_ref = 0
        for f in ref_dosyalar:
            if toplam_ref >= MAX_CHARS_REF_TOT:
                print(f"  Referans toplam limit ({MAX_CHARS_REF_TOT:,}) aşıldı, {f.name} atlandı")
                break
            try:
                metin = dosya_oku(f, MAX_CHARS_REF)
                try:
                    rel = str(f.relative_to(REF_DIR))
                except ValueError:
                    rel = f.name
                ref_metinler.append(f"#### {rel}\n{metin}")
                toplam_ref += len(metin)
            except Exception:
                pass
        if ref_metinler:
            icerik_parcalari.append({
                "type": "text",
                "text": (
                    "### REFERANS DOKÜMANLAR\n"
                    "Mevcut endpoint'leri kullan, uydurma.\n\n"
                    + "\n\n---\n\n".join(ref_metinler)
                ),
            })

    icerik_parcalari.append({"type": "text", "text": f"### Süreç Analizi\n\n{surec_metni}"})

    if mockup_icerik:
        print(f"  HTML prototip dahil ediliyor ({len(mockup_icerik):,} karakter)...")
        icerik_parcalari.append({"type": "text", "text": f"### HTML Prototip\n\n{mockup_icerik}"})

    if ui_kodu:
        print(f"  UI kodu dahil ediliyor ({len(ui_kodu):,} karakter)...")
        icerik_parcalari.append({"type": "text", "text": f"### Mevcut UI Kodu\n\n{ui_kodu}"})

    icerik_parcalari.append({"type": "text", "text": "Teknik analiz raporunu ve açık soruları üret."})

    sistem = _teknik_prompt_olustur(ui_kodu, mockup_var=bool(mockup_icerik))
    mesajlar = [{"role": "user", "content": icerik_parcalari}]
    yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_COMBINED, thinking=extended_thinking_acik())
    yanit = _metin_sikistir(yanit)

    teknik  = _xml_ayir(yanit, "teknik_analiz")
    sorular = _xml_ayir(yanit, "acik_sorular")

    teknik_yol  = _kaydet("teknik-analiz.md", teknik)
    sorular_yol = _kaydet("acik-sorular.md", sorular)

    return teknik_yol, sorular_yol
