"""
Orchestrator — app.py tarafından subprocess ile çağrılır.

Kullanım:
  python run.py surec_analizi
  python run.py teknik_analiz
  python run.py brd_analizi
  python run.py kapsam_analizi
  python run.py jira_gonder
  python run.py yeniden_calistir <hedef_dosya> <duzeltme_notu_dosyasi>
"""

import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import workflow
from workflow import Durum


def _tamamlandi(durum: str, mesaj: str) -> None:
    try:
        workflow.guncelle(durum, mesaj)
    except ValueError as e:
        # Analiz BAŞARIYLA bitti ama state bu sırada dışarıdan değişmiş
        # (sıfırlanmış vb.) olabilir — sonucu kaybetme, durumu zorla yaz.
        # Aksi halde subprocess exit 1 olur ve üretilen çıktı UI'da
        # "yok" gibi görünürdü.
        print(f"[UYARI] Workflow geçişi reddedildi ({e}) — durum zorla yazılıyor.")
        workflow.zorla_durum(durum, mesaj)
    print(f"[TAMAMLANDI] {mesaj}")


def _hata(mesaj: str) -> None:
    try:
        workflow.guncelle(Durum.HATA, mesaj, hata=mesaj)
    except Exception:
        pass
    print(f"[HATA] {mesaj}", file=sys.stderr)


def calistir_surec_analizi() -> None:
    from agent import surec_analizi_yap
    try:
        yol = surec_analizi_yap()
        _tamamlandi(Durum.ONAY_BEKLENIYOR, f"Süreç analizi tamamlandı → {yol.name}")
    except Exception as e:
        _hata(f"Süreç analizi hatası: {e}\n{traceback.format_exc()}")
        sys.exit(1)


def calistir_teknik_analiz() -> None:
    from agent import teknik_analiz_yap
    try:
        teknik, sorular = teknik_analiz_yap()
        _tamamlandi(Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR, f"Teknik analiz tamamlandı → {teknik.name}, {sorular.name}")
    except Exception as e:
        _hata(f"Teknik analiz hatası: {e}\n{traceback.format_exc()}")
        sys.exit(1)


def calistir_brd_analizi() -> None:
    from agent import brd_analizi_yap
    try:
        analiz, sorular = brd_analizi_yap()
        _tamamlandi(Durum.BRD_REVIZE_BEKLENIYOR, f"BRD analizi tamamlandı → {analiz.name}, {sorular.name}")
    except Exception as e:
        _hata(f"BRD analizi hatası: {e}\n{traceback.format_exc()}")
        sys.exit(1)


def calistir_kapsam_analizi() -> None:
    from agent import kapsam_analizi_yap, brd_final_kaydet
    try:
        kapsam, alternatif = kapsam_analizi_yap()
        brd_final_kaydet()
        _tamamlandi(Durum.BRD_TAMAMLANDI, f"Kapsam analizi tamamlandı → {kapsam.name}, {alternatif.name}")
    except Exception as e:
        _hata(f"Kapsam analizi hatası: {e}\n{traceback.format_exc()}")
        sys.exit(1)


def calistir_jira_gonder() -> None:
    from jira_agent import main as jira_main
    try:
        task_key, task_basligi = jira_main()
        _tamamlandi(Durum.JIRA_TAMAMLANDI, f"Jira task: {task_key} — {task_basligi}")
    except Exception as e:
        _hata(f"Jira gönderim hatası: {e}\n{traceback.format_exc()}")
        sys.exit(1)


def calistir_yeniden(hedef_dosya: str, notu_dosya: str) -> None:
    """
    Mevcut çıktıyı düzeltme notu dosyasından okuyarak yeniden üretir.
    Workflow state değiştirmez — bağımsız çalışır.
    """
    from agent import yeniden_calistir
    try:
        notu_yol = Path(notu_dosya)
        if not notu_yol.exists():
            raise FileNotFoundError(f"Düzeltme notu dosyası bulunamadı: {notu_dosya}")
        duzeltme_notu = notu_yol.read_text(encoding="utf-8").strip()
        if not duzeltme_notu:
            raise ValueError("Düzeltme notu boş.")
        yol = yeniden_calistir(hedef_dosya, duzeltme_notu)
        print(f"[TAMAMLANDI] Yeniden üretildi → {yol.name}")
    except Exception as e:
        print(f"[HATA] {e}\n{traceback.format_exc()}", file=sys.stderr)
        sys.exit(1)


MODLAR = {
    "surec_analizi":  calistir_surec_analizi,
    "teknik_analiz":  calistir_teknik_analiz,
    "brd_analizi":    calistir_brd_analizi,
    "kapsam_analizi": calistir_kapsam_analizi,
    "jira_gonder":    calistir_jira_gonder,
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Kullanım: python run.py [{' | '.join(MODLAR)} | yeniden_calistir <dosya> <notu>]")
        sys.exit(1)

    mod = sys.argv[1]

    if mod == "yeniden_calistir":
        if len(sys.argv) < 4:
            print("Kullanım: python run.py yeniden_calistir <hedef_dosya> <notu_dosya>")
            sys.exit(1)
        print(f"[MOD] yeniden_calistir: {sys.argv[2]}")
        calistir_yeniden(sys.argv[2], sys.argv[3])
    elif mod in MODLAR:
        print(f"[MOD] {mod} başlatılıyor...")
        MODLAR[mod]()
    else:
        print(f"Bilinmeyen mod: {mod}")
        sys.exit(1)
