"""
Workflow state machine — aşamalı onay mekanizması.

Süreç Pipeline:
  idle → surec_analizi_calisiyor → onay_bekleniyor
       → teknik_analiz_calisiyor → teknik_analiz_onay_bekleniyor
       → jira_gonderiliyor → jira_tamamlandi

BRD Pipeline:
  idle → brd_analizi_calisiyor → brd_revize_bekleniyor → kapsam_analizi_calisiyor → brd_tamamlandi
"""

import json
import time
import threading
from pathlib import Path
from enum import Enum

WORKFLOW_FILE = Path(__file__).parent / "output" / "workflow-state.json"

_wf_lock = threading.RLock()  # Reentrant — aynı thread içinde tekrar alınabilir


class Durum(str, Enum):
    IDLE                             = "idle"
    # Süreç pipeline
    SUREC_ANALIZI_CALISIYOR          = "surec_analizi_calisiyor"
    ONAY_BEKLENIYOR                  = "onay_bekleniyor"
    TEKNIK_ANALIZ_CALISIYOR          = "teknik_analiz_calisiyor"
    TEKNIK_ANALIZ_ONAY_BEKLENIYOR    = "teknik_analiz_onay_bekleniyor"
    JIRA_GONDERILIYOR                = "jira_gonderiliyor"
    JIRA_TAMAMLANDI                  = "jira_tamamlandi"
    SUREC_TAMAMLANDI                 = "surec_tamamlandi"   # eski veri uyumluluğu
    # BRD pipeline
    BRD_ANALIZI_CALISIYOR            = "brd_analizi_calisiyor"
    BRD_REVIZE_BEKLENIYOR            = "brd_revize_bekleniyor"
    KAPSAM_ANALIZI_CALISIYOR         = "kapsam_analizi_calisiyor"
    BRD_TAMAMLANDI                   = "brd_tamamlandi"
    # Hata
    HATA                             = "hata"


GECERLI_GECISLER: dict[str, list[str]] = {
    Durum.IDLE:                            [Durum.SUREC_ANALIZI_CALISIYOR, Durum.BRD_ANALIZI_CALISIYOR, Durum.TEKNIK_ANALIZ_CALISIYOR],
    Durum.SUREC_ANALIZI_CALISIYOR:         [Durum.ONAY_BEKLENIYOR, Durum.HATA],
    Durum.ONAY_BEKLENIYOR:                 [Durum.TEKNIK_ANALIZ_CALISIYOR, Durum.IDLE],
    Durum.TEKNIK_ANALIZ_CALISIYOR:         [Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR, Durum.HATA],
    Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR:   [Durum.JIRA_GONDERILIYOR, Durum.SUREC_TAMAMLANDI, Durum.IDLE],
    Durum.JIRA_GONDERILIYOR:               [Durum.JIRA_TAMAMLANDI, Durum.HATA],
    Durum.JIRA_TAMAMLANDI:                 [Durum.IDLE],
    Durum.SUREC_TAMAMLANDI:                [Durum.IDLE],
    Durum.BRD_ANALIZI_CALISIYOR:           [Durum.BRD_REVIZE_BEKLENIYOR, Durum.HATA],
    Durum.BRD_REVIZE_BEKLENIYOR:           [Durum.KAPSAM_ANALIZI_CALISIYOR, Durum.IDLE],
    Durum.KAPSAM_ANALIZI_CALISIYOR:        [Durum.BRD_TAMAMLANDI, Durum.HATA],
    Durum.BRD_TAMAMLANDI:                  [Durum.IDLE],
    Durum.HATA:                            [Durum.IDLE],
}

DURUM_ETIKET: dict[str, str] = {
    Durum.IDLE:                            "Hazır",
    Durum.SUREC_ANALIZI_CALISIYOR:         "Süreç analizi yapılıyor...",
    Durum.ONAY_BEKLENIYOR:                 "Analist onayı bekleniyor",
    Durum.TEKNIK_ANALIZ_CALISIYOR:         "Teknik analiz yapılıyor...",
    Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR:   "Teknik analiz onayı bekleniyor",
    Durum.JIRA_GONDERILIYOR:               "Jira task oluşturuluyor...",
    Durum.JIRA_TAMAMLANDI:                 "Jira task oluşturuldu",
    Durum.SUREC_TAMAMLANDI:                "Tamamlandı",
    Durum.BRD_ANALIZI_CALISIYOR:           "BRD analizi yapılıyor...",
    Durum.BRD_REVIZE_BEKLENIYOR:           "Product Owner revizyonu bekleniyor",
    Durum.KAPSAM_ANALIZI_CALISIYOR:        "Kapsam analizi yapılıyor...",
    Durum.BRD_TAMAMLANDI:                  "BRD pipeline tamamlandı",
    Durum.HATA:                            "Hata oluştu",
}

CALISMA_DURUMLARI = {
    Durum.SUREC_ANALIZI_CALISIYOR,
    Durum.TEKNIK_ANALIZ_CALISIYOR,
    Durum.BRD_ANALIZI_CALISIYOR,
    Durum.KAPSAM_ANALIZI_CALISIYOR,
    Durum.JIRA_GONDERILIYOR,
}


def _bos_durum() -> dict:
    return {
        "durum": Durum.IDLE,
        "pipeline": None,
        "guncelleme": time.time(),
        "mesaj": "",
        "hata": None,
        "onaylandi": None,
        "adimlar": [],
    }


def oku() -> dict:
    with _wf_lock:
        try:
            if WORKFLOW_FILE.exists():
                return json.loads(WORKFLOW_FILE.read_text())
        except Exception:
            pass
        return _bos_durum()


def _kaydet(state: dict) -> None:
    with _wf_lock:
        WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        state["guncelleme"] = time.time()
        tmp = WORKFLOW_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        tmp.replace(WORKFLOW_FILE)  # POSIX'te atomik


def guncelle(yeni_durum: str, mesaj: str = "", hata: str | None = None) -> dict:
    state = oku()
    mevcut = state["durum"]

    izinliler = GECERLI_GECISLER.get(mevcut, [])
    if yeni_durum not in izinliler:
        raise ValueError(f"Geçersiz geçiş: {mevcut} → {yeni_durum}")

    state["durum"] = yeni_durum
    state["mesaj"] = mesaj
    state["hata"] = hata

    adim = {"durum": yeni_durum, "zaman": time.time(), "mesaj": mesaj}
    state["adimlar"].append(adim)

    if yeni_durum in (Durum.IDLE,):
        state["onaylandi"] = None

    _kaydet(state)
    return state


def baslat(pipeline: str) -> dict:
    """Pipeline'ı başlatır. pipeline: 'surec' veya 'brd'

    Yalnızca GERÇEKTEN çalışan bir analiz varken reddedilir. HATA, onay
    bekleme veya tamamlanmış durumlardan otomatik temiz başlangıç yapılır —
    kullanıcı hata sonrası dosya/log silmek ya da elle sıfırlamak zorunda
    kalmaz: yeni dosya yükle → çalıştır → temiz başlar.
    """
    state = oku()
    if state["durum"] in CALISMA_DURUMLARI:
        raise ValueError(f"Aktif workflow var: {state['durum']}")

    state = _bos_durum()
    state["pipeline"] = pipeline

    yeni = (
        Durum.SUREC_ANALIZI_CALISIYOR
        if pipeline == "surec"
        else Durum.BRD_ANALIZI_CALISIYOR
    )
    state["durum"] = yeni
    state["mesaj"] = DURUM_ETIKET[yeni]
    state["adimlar"].append({"durum": yeni, "zaman": time.time(), "mesaj": state["mesaj"]})
    _kaydet(state)
    return state


def baslat_teknik() -> dict:
    """Mevcut süreç analizi üzerinden doğrudan teknik analiz başlatır.

    baslat() ile aynı kurtarma kuralı: yalnız aktif çalışma reddedilir;
    HATA / bekleme / tamamlanmış durumlardan temiz başlanır.
    """
    state = oku()
    if state["durum"] in CALISMA_DURUMLARI:
        raise ValueError(f"Aktif workflow var: {state['durum']}")

    state = _bos_durum()
    state["pipeline"] = "surec"
    state["durum"] = Durum.TEKNIK_ANALIZ_CALISIYOR
    state["mesaj"] = DURUM_ETIKET[Durum.TEKNIK_ANALIZ_CALISIYOR]
    state["adimlar"].append({"durum": Durum.TEKNIK_ANALIZ_CALISIYOR, "zaman": time.time(), "mesaj": state["mesaj"]})
    _kaydet(state)
    return state


def onayla() -> dict:
    """Süreç analizi onayı — ONAY_BEKLENIYOR → TEKNIK_ANALIZ_CALISIYOR"""
    state = oku()
    if state["durum"] != Durum.ONAY_BEKLENIYOR:
        raise ValueError(f"Onay beklenmiyor, mevcut durum: {state['durum']}")
    state["onaylandi"] = True
    _kaydet(state)
    return guncelle(Durum.TEKNIK_ANALIZ_CALISIYOR, "Teknik analiz başlatılıyor...")


def reddet() -> dict:
    """Süreç analizi reddi — ONAY_BEKLENIYOR → IDLE"""
    state = oku()
    if state["durum"] != Durum.ONAY_BEKLENIYOR:
        raise ValueError(f"Onay beklenmiyor, mevcut durum: {state['durum']}")
    state["onaylandi"] = False
    _kaydet(state)
    return guncelle(Durum.IDLE, "Analist tarafından reddedildi.")


def teknik_onayla() -> dict:
    """Teknik analiz onayı — TEKNIK_ANALIZ_ONAY_BEKLENIYOR → JIRA_GONDERILIYOR"""
    state = oku()
    if state["durum"] != Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR:
        raise ValueError(f"Teknik analiz onayı beklenmiyor, mevcut durum: {state['durum']}")
    return guncelle(Durum.JIRA_GONDERILIYOR, "Jira task oluşturuluyor...")


def teknik_bitir() -> dict:
    """Jira olmadan tamamla — TEKNIK_ANALIZ_ONAY_BEKLENIYOR → SUREC_TAMAMLANDI"""
    state = oku()
    if state["durum"] != Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR:
        raise ValueError(f"Teknik analiz onayı beklenmiyor, mevcut durum: {state['durum']}")
    return guncelle(Durum.SUREC_TAMAMLANDI, "Teknik analiz tamamlandı.")


def teknik_reddet() -> dict:
    """Teknik analiz reddi — TEKNIK_ANALIZ_ONAY_BEKLENIYOR → IDLE"""
    state = oku()
    if state["durum"] != Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR:
        raise ValueError(f"Teknik analiz onayı beklenmiyor, mevcut durum: {state['durum']}")
    return guncelle(Durum.IDLE, "Teknik analiz reddedildi.")


def brd_revize_tamamlandi() -> dict:
    """BRD revize yüklendi — BRD_REVIZE_BEKLENIYOR → KAPSAM_ANALIZI_CALISIYOR"""
    state = oku()
    if state["durum"] != Durum.BRD_REVIZE_BEKLENIYOR:
        raise ValueError(f"BRD revizyonu beklenmiyor, mevcut durum: {state['durum']}")
    return guncelle(Durum.KAPSAM_ANALIZI_CALISIYOR, "Kapsam analizi başlatılıyor...")


def sifirla() -> dict:
    """Workflow'u sıfırla → IDLE"""
    state = _bos_durum()
    _kaydet(state)
    return state


def calisiyor_mu() -> bool:
    return oku()["durum"] in CALISMA_DURUMLARI


def ozet() -> dict:
    state = oku()
    durum = state["durum"]
    return {
        "durum": durum,
        "etiket": DURUM_ETIKET.get(durum, durum),
        "pipeline": state["pipeline"],
        "mesaj": state["mesaj"],
        "hata": state["hata"],
        "onaylandi": state["onaylandi"],
        "calisiyor": durum in CALISMA_DURUMLARI,
        "onay_bekleniyor": durum == Durum.ONAY_BEKLENIYOR,
        "teknik_onay_bekleniyor": durum == Durum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR,
        "brd_revize_bekleniyor": durum == Durum.BRD_REVIZE_BEKLENIYOR,
        "jira_tamamlandi": durum == Durum.JIRA_TAMAMLANDI,
        "tamamlandi": durum in (Durum.SUREC_TAMAMLANDI, Durum.BRD_TAMAMLANDI, Durum.JIRA_TAMAMLANDI),
    }
