#!/usr/bin/env python3
"""
BRD Analyst Agent — CLI

Kullanım:
  python cli.py surec <dosya>               Süreç analizi
  python cli.py surec <dosya> --teknik      Süreç + teknik analiz (onay adımı yok)
  python cli.py brd <dosya>                 BRD analizi + sorular
  python cli.py brd <dosya> --revize <r>    BRD + kapsam analizi
  python cli.py rerun <hedef> "<not>"       Mevcut çıktıyı düzelt
  python cli.py ui <klasör_veya_zip>        UI kodu yükle

  python cli.py --help
"""

import sys
import shutil
import argparse
import textwrap
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


# ─── Renkli çıktı ────────────────────────────────────────────────────────────

def _destekli() -> bool:
    import os
    return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"


RENK = _destekli()

def _c(kod: str, metin: str) -> str:
    return f"\033[{kod}m{metin}\033[0m" if RENK else metin

def baslik(metin: str) -> None:
    print(_c("1;34", f"\n▶ {metin}"))

def basari(metin: str) -> None:
    print(_c("1;32", f"  ✓ {metin}"))

def hata(metin: str) -> None:
    print(_c("1;31", f"  ✗ {metin}"), file=sys.stderr)

def bilgi(metin: str) -> None:
    print(_c("90", f"  {metin}"))

def uyari(metin: str) -> None:
    print(_c("1;33", f"  ⚠ {metin}"))


# ─── Ortam kontrol ────────────────────────────────────────────────────────────

def _env_kontrol() -> bool:
    from dotenv import load_dotenv
    import os
    load_dotenv(BASE_DIR / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        hata("ANTHROPIC_API_KEY tanımlı değil.")
        bilgi(".env dosyasına ekleyin:  ANTHROPIC_API_KEY=sk-ant-...")
        bilgi("Veya: export ANTHROPIC_API_KEY=sk-ant-...")
        return False
    return True


# ─── Input hazırla ───────────────────────────────────────────────────────────

def _input_koy(dosya_yolu: str) -> Path:
    """Verilen dosyayı input/ klasörüne kopyala."""
    kaynak = Path(dosya_yolu).expanduser().resolve()
    if not kaynak.exists():
        hata(f"Dosya bulunamadı: {kaynak}")
        sys.exit(1)

    input_dir = BASE_DIR / "input"
    input_dir.mkdir(exist_ok=True)

    for eski in input_dir.iterdir():
        if eski.is_file():
            eski.unlink()

    hedef = input_dir / kaynak.name
    shutil.copy2(kaynak, hedef)
    bilgi(f"Input: {kaynak.name}  ({_boyut(kaynak)})")
    return hedef


def _boyut(p: Path) -> str:
    b = p.stat().st_size
    if b < 1024:       return f"{b} B"
    if b < 1048576:    return f"{b/1024:.1f} KB"
    return f"{b/1048576:.1f} MB"


def _cikti_goster(dosyalar: list[str]) -> None:
    for ad in dosyalar:
        yol = BASE_DIR / "output" / ad
        if yol.exists():
            basari(f"{ad}  ({_boyut(yol)})")
            bilgi(f"   → {yol}")


# ─── Komutlar ────────────────────────────────────────────────────────────────

def cmd_surec(args) -> None:
    """Süreç analizi — opsiyonel olarak teknik analiz de üretir."""
    if not _env_kontrol():
        sys.exit(1)

    _input_koy(args.dosya)

    from agent import surec_analizi_yap

    baslik("Süreç Analizi")
    yol = surec_analizi_yap()
    basari(f"Süreç analizi tamamlandı → {yol.name}")

    if args.teknik:
        from agent import teknik_analiz_yap
        baslik("Teknik Analiz")
        teknik, sorular = teknik_analiz_yap()
        basari(f"Teknik analiz → {teknik.name}")
        basari(f"Açık sorular  → {sorular.name}")
        _cikti_goster(["surec-analizi.md", "teknik-analiz.md", "acik-sorular.md"])
    else:
        uyari("Teknik analizi de üretmek için: --teknik flag'ini ekleyin")
        _cikti_goster(["surec-analizi.md"])


def cmd_brd(args) -> None:
    """BRD analizi — opsiyonel kapsam analizi."""
    if not _env_kontrol():
        sys.exit(1)

    _input_koy(args.dosya)

    from agent import brd_analizi_yap

    baslik("BRD Analizi")
    analiz, sorular = brd_analizi_yap()
    basari(f"BRD analizi  → {analiz.name}")
    basari(f"BRD soruları → {sorular.name}")

    if args.revize:
        _input_koy(args.revize)
        from agent import kapsam_analizi_yap, brd_final_kaydet

        baslik("Kapsam Analizi")
        kapsam, alternatif = kapsam_analizi_yap()
        brd_final_kaydet()
        basari(f"Kapsam analizi   → {kapsam.name}")
        basari(f"Alternatif süreç → {alternatif.name}")
        basari("Revize BRD baseline olarak kaydedildi.")
        _cikti_goster(["brd-analizi.md", "brd-sorular.md", "kapsam-analizi.md", "alternatif-surecler.md"])
    else:
        uyari("Kapsam analizi için revize BRD'yi hazırladıktan sonra: --revize <dosya>")
        _cikti_goster(["brd-analizi.md", "brd-sorular.md"])


def cmd_rerun(args) -> None:
    """Mevcut çıktıyı düzeltme notu ile yeniden üret."""
    if not _env_kontrol():
        sys.exit(1)

    IZIN = {
        "surec-analizi.md", "teknik-analiz.md", "acik-sorular.md",
        "brd-analizi.md", "brd-sorular.md",
        "kapsam-analizi.md", "alternatif-surecler.md",
    }
    if args.hedef not in IZIN:
        hata(f"Geçersiz hedef. Kabul edilenler:\n  {chr(10).join(sorted(IZIN))}")
        sys.exit(1)

    from agent import yeniden_calistir

    baslik(f"Yeniden Üretme: {args.hedef}")
    bilgi(f"Not: {args.duzeltme_notu[:80]}{'...' if len(args.duzeltme_notu)>80 else ''}")
    yol = yeniden_calistir(args.hedef, args.duzeltme_notu)
    basari(f"Tamamlandı → {yol}")


def cmd_ui(args) -> None:
    """UI kodu yükle — zip dosyası veya klasör."""
    import zipfile as _zf

    kaynak = Path(args.kaynak).expanduser().resolve()
    if not kaynak.exists():
        hata(f"Kaynak bulunamadı: {kaynak}")
        sys.exit(1)

    from agent import UI_UZANTILAR, UI_CODE_DIR, _metin_kes

    ui_dir = UI_CODE_DIR
    ui_dir.mkdir(parents=True, exist_ok=True)

    ATLA = {
        "node_modules", ".git", "__pycache__", "dist", "build",
        ".next", ".nuxt", "coverage", ".cache", ".vite", "out",
    }

    if kaynak.suffix.lower() == ".zip":
        baslik(f"Zip Çıkartılıyor: {kaynak.name}")
        if args.temizle:
            shutil.rmtree(ui_dir, ignore_errors=True)
            ui_dir.mkdir(parents=True, exist_ok=True)

        yuklenen = atlanan = 0
        with _zf.ZipFile(str(kaynak)) as zf:
            for uye in zf.infolist():
                if uye.is_dir():
                    continue
                p = Path(uye.filename)
                if any(parca in ATLA for parca in p.parts):
                    atlanan += 1
                    continue
                if p.suffix.lower() not in UI_UZANTILAR:
                    atlanan += 1
                    continue
                if uye.file_size > 512 * 1024:
                    atlanan += 1
                    continue
                hedef = (ui_dir / uye.filename).resolve()
                if not str(hedef).startswith(str(ui_dir.resolve())):
                    atlanan += 1
                    continue
                hedef.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(uye) as src:
                    hedef.write_bytes(src.read())
                yuklenen += 1

        basari(f"{yuklenen} dosya yüklendi  ({atlanan} atlandı)")
        bilgi(f"Hedef: {ui_dir}")

    elif kaynak.is_dir():
        baslik(f"Klasör Yükleniyor: {kaynak.name}")
        if args.temizle:
            shutil.rmtree(ui_dir, ignore_errors=True)
            ui_dir.mkdir(parents=True, exist_ok=True)

        yuklenen = atlanan = 0
        for f in kaynak.rglob("*"):
            if not f.is_file():
                continue
            if any(parca in ATLA for parca in f.relative_to(kaynak).parts):
                atlanan += 1
                continue
            if f.suffix.lower() not in UI_UZANTILAR:
                atlanan += 1
                continue
            goreceli = f.relative_to(kaynak)
            hedef = ui_dir / goreceli
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, hedef)
            yuklenen += 1

        basari(f"{yuklenen} dosya yüklendi  ({atlanan} atlandı)")
        bilgi(f"Hedef: {ui_dir}")

    else:
        hata("Kaynak bir .zip dosyası veya klasör olmalıdır.")
        sys.exit(1)


# ─── Argparse ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            BRD Analyst Agent — CLI
            Web UI olmadan terminal üzerinden çalıştırır.
        """),
    )
    sub = parser.add_subparsers(dest="komut", metavar="komut")

    # surec
    p_surec = sub.add_parser("surec", help="Süreç analizi pipeline")
    p_surec.add_argument("dosya", help="Analiz edilecek dosya (PDF, DOCX, TXT, MD, PNG)")
    p_surec.add_argument("--teknik", action="store_true",
                         help="Onay adımı olmadan teknik analiz + açık soruları da üret")

    # brd
    p_brd = sub.add_parser("brd", help="BRD analizi pipeline")
    p_brd.add_argument("dosya", help="BRD dosyası (PDF, DOCX, TXT, MD)")
    p_brd.add_argument("--revize", metavar="DOSYA",
                       help="Revize edilmiş BRD — kapsam analizi + alternatif süreçler için")

    # rerun
    p_rerun = sub.add_parser("rerun", help="Mevcut çıktıyı düzeltme notu ile yeniden üret")
    p_rerun.add_argument("hedef",
                         choices=[
                             "surec-analizi.md", "teknik-analiz.md", "acik-sorular.md",
                             "brd-analizi.md", "brd-sorular.md",
                             "kapsam-analizi.md", "alternatif-surecler.md",
                         ],
                         help="Yeniden üretilecek çıktı dosyası")
    p_rerun.add_argument("duzeltme_notu", metavar="NOT",
                         help="Düzeltme notu (tırnak içinde)")

    # ui
    p_ui = sub.add_parser("ui", help="UI kodu yükle (zip veya klasör)")
    p_ui.add_argument("kaynak", help="Zip dosyası veya klasör yolu")
    p_ui.add_argument("--temizle", action="store_true", default=True,
                      help="Yüklemeden önce mevcut UI dosyalarını temizle (varsayılan: açık)")
    p_ui.add_argument("--ekle", dest="temizle", action="store_false",
                      help="Mevcut UI dosyalarını koruyarak üzerine ekle")

    args = parser.parse_args()

    if not args.komut:
        parser.print_help()
        sys.exit(0)

    KOMUTLAR = {
        "surec":  cmd_surec,
        "brd":    cmd_brd,
        "rerun":  cmd_rerun,
        "ui":     cmd_ui,
    }
    try:
        KOMUTLAR[args.komut](args)
    except KeyboardInterrupt:
        print(_c("90", "\n  İptal edildi."))
        sys.exit(130)
    except Exception as e:
        hata(str(e))
        import traceback
        bilgi(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
