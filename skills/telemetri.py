"""Kullanım telemetrisi — analiz olaylarını loglar (yalnız metadata, doküman içeriği ASLA).

Tasarım:
- Lokal instance başına append-only JSONL: logs/usage/events.jsonl
- İsteğe bağlı uzak "sink" (USAGE_SINK_URL): fire-and-forget POST — başarısız olursa sessiz.
- Owner (yalnız sen) tarafında dashboard bu olayları okuyup toplar (0-token, deterministik).
- FAIL-SAFE: hiçbir fonksiyon analizi bloklamaz/bozmaz; tüm çağrılar try/except ile izole.

Gizlilik: yalnız metadata (analist, olay tipi, süre, durum, model, açılan task adedi, bağlam
başlıkları) tutulur. BRD/analiz metni ASLA loglanmaz.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
USAGE_DIR = BASE_DIR / "logs" / "usage"
EVENTS_DOSYA = USAGE_DIR / "events.jsonl"          # bu makinenin kendi olayları
UZAK_DOSYA = USAGE_DIR / "remote.jsonl"            # owner: sink'ten çekilen ekip verisi
ANALIST_DOSYA = BASE_DIR / "analist.json"          # UI'dan girilen ad-soyad (gitignore)

# Toplayıcı (Apps Script) varsayılan URL — analist makineleri hiçbir şey ayarlamasın diye
# gömülü. Yalnız-YAZMA endpoint'i (okuma OKUMA_ANAHTARI ister). USAGE_SINK_URL env geçersizler.
VARSAYILAN_SINK_URL = "https://script.google.com/macros/s/AKfycbzxMWtRqoTmgWFyc9_LrsNS-ZOK4HvT5BxjB_x8nLL29D77NBklAcImtyNNdyN_xIiF/exec"


def _sink_url() -> str:
    return os.getenv("USAGE_SINK_URL", "").strip() or VARSAYILAN_SINK_URL


def analist_oku() -> str:
    """UI'dan kaydedilen analist ad-soyad. Yoksa ''."""
    try:
        d = json.loads(ANALIST_DOSYA.read_text(encoding="utf-8"))
        return str(d.get("ad_soyad", "")).strip()
    except Exception:
        return ""


def analist_yaz(ad_soyad: str) -> None:
    try:
        ANALIST_DOSYA.write_text(
            json.dumps({"ad_soyad": (ad_soyad or "").strip()}, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        pass

# Geçerli olay tipleri (dashboard kırılımı bunlara göre)
OLAY_TIPLERI = (
    "surec_analizi", "teknik_analiz", "brd_analizi",
    "kapsam_analizi", "gorev_analiz", "mutabakat", "jira_gonder",
)


# Jira task sayacı — bir jira_gonder run'ında açılan issue adedi (hem jira_agent tek-Task
# yolu hem jira_tasks hiyerarşi yolu buraya artırır; run.py okur). Aynı subprocess içinde
# TEK modül örneği (herkes `skills.telemetri` olarak import etmeli).
_JIRA_SAYAC = {"toplam": 0}


def jira_task_arttir(n: int = 1) -> None:
    try:
        _JIRA_SAYAC["toplam"] += n
    except Exception:
        pass


def jira_sayac_sifirla() -> None:
    _JIRA_SAYAC["toplam"] = 0


def jira_sayac_oku() -> dict:
    return dict(_JIRA_SAYAC)


def _analist_belirle(acik: str | None = None) -> str:
    """Analist kimliği önceliği:
    açıkça verilen (login username) > ANALIST env > analist.json (UI ad-soyad)
    > ANALYST_NAME env > OS kullanıcısı."""
    for aday in (acik, os.getenv("ANALIST"), analist_oku(), os.getenv("ANALYST_NAME")):
        if aday and str(aday).strip():
            return str(aday).strip()
    try:
        return getpass.getuser()
    except Exception:
        return "bilinmeyen"


def _app_versiyon() -> str:
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE_DIR),
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        ).strip()
    except Exception:
        return ""


def _sink_gonder(olay: dict) -> None:
    """Uzak toplayıcıya (Apps Script vb.) fire-and-forget POST. Hata yutulur."""
    url = _sink_url()
    if not url:
        return

    def _gonder():
        try:
            import requests  # certifi CA paketi → macOS SSL doğrulaması sorunsuz
            requests.post(url, json=olay, timeout=5)
        except Exception:
            pass  # transport başarısız → lokal JSONL yedek zaten var

    threading.Thread(target=_gonder, daemon=True).start()


def olay_yaz(
    olay: str,
    durum: str = "ok",
    analist: str | None = None,
    sure_ms: int | None = None,
    model: str | None = None,
    ai_modu: str | None = None,
    jira: dict | None = None,
    baglam: dict | None = None,
) -> None:
    """Tek kullanım olayını lokal JSONL'e yazar + uzak sink'e gönderir. Asla hata fırlatmaz."""
    try:
        kayit = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "analist": _analist_belirle(analist),
            "olay": olay,
            "durum": durum,
            "sure_ms": sure_ms,
            "model": model,
            "ai_modu": ai_modu,
            "jira": jira or None,
            "baglam": baglam or None,
            "makine": socket.gethostname(),
            "app_versiyon": _app_versiyon(),
        }
        USAGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(EVENTS_DOSYA, "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
        _sink_gonder(kayit)
    except Exception:
        pass  # telemetri asla analizi bozmaz


def olaylari_oku() -> list[dict]:
    """logs/usage altındaki tüm .jsonl dosyalarını (lokal + uzak) okuyup birleştirir. Owner dashboard için."""
    olaylar: list[dict] = []
    try:
        if not USAGE_DIR.exists():
            return olaylar
        for yol in sorted(USAGE_DIR.glob("*.jsonl")):
            try:
                for satir in yol.read_text(encoding="utf-8").splitlines():
                    satir = satir.strip()
                    if not satir:
                        continue
                    try:
                        olaylar.append(json.loads(satir))
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return olaylar


def istatistik(gun: int = 90) -> dict:
    """Deterministik, 0-token özet: analist × olay tipi, başarı, süre, Jira task, zaman serisi."""
    olaylar = olaylari_oku()
    kesim = time.time() - gun * 86400
    filtreli = []
    for e in olaylar:
        try:
            ts = datetime.fromisoformat(str(e.get("ts", ""))).timestamp()
            if ts >= kesim:
                filtreli.append(e)
        except Exception:
            filtreli.append(e)  # ts parse edilemezse dahil et

    analistler: dict[str, dict] = {}
    tip_toplam: dict[str, int] = {}
    gunluk: dict[str, int] = {}
    toplam_task = 0

    for e in filtreli:
        a = e.get("analist") or "bilinmeyen"
        olay = e.get("olay") or "diger"
        durum = e.get("durum") or "ok"
        sure = e.get("sure_ms") or 0
        jira = e.get("jira") or {}
        task_adedi = int(jira.get("toplam", 0)) if isinstance(jira, dict) else 0

        an = analistler.setdefault(a, {
            "analist": a, "toplam": 0, "basarili": 0, "hatali": 0,
            "sure_ms_toplam": 0, "jira_task": 0, "tipler": {},
        })
        an["toplam"] += 1
        an["basarili" if durum == "ok" else "hatali"] += 1
        an["sure_ms_toplam"] += sure
        an["jira_task"] += task_adedi
        an["tipler"][olay] = an["tipler"].get(olay, 0) + 1

        tip_toplam[olay] = tip_toplam.get(olay, 0) + 1
        toplam_task += task_adedi
        gun_k = str(e.get("ts", ""))[:10]
        if gun_k:
            gunluk[gun_k] = gunluk.get(gun_k, 0) + 1

    for an in analistler.values():
        an["ort_sure_ms"] = round(an["sure_ms_toplam"] / an["toplam"]) if an["toplam"] else 0

    # İsim bazında SABİT sıralama + id (Emin=1, Denizhan=2 gibi; aynı kadro → aynı id).
    # Türkçe harfler için casefold ile deterministik sıralama.
    sirali = sorted(analistler.values(), key=lambda x: str(x["analist"]).casefold())
    for i, an in enumerate(sirali, start=1):
        an["id"] = i

    return {
        "gun": gun,
        "toplam_analiz": len(filtreli),
        "toplam_jira_task": toplam_task,
        "analist_sayisi": len(analistler),
        "analistler": sirali,
        "tip_toplam": tip_toplam,
        "gunluk": dict(sorted(gunluk.items())),
    }


def uzaktan_cek() -> tuple[bool, str]:
    """Owner: uzak sink'ten (Apps Script GET) ekip olaylarını çekip remote.jsonl'e yazar.

    USAGE_SINK_URL + USAGE_SINK_KEY gerektirir. Apps Script ?read=<key> ile JSON dizi döndürür.
    """
    url = _sink_url()
    key = os.getenv("USAGE_SINK_KEY", "").strip()
    if not url:
        return False, "USAGE_SINK_URL tanımlı değil."
    try:
        import requests
        r = requests.get(url, params={"read": key}, timeout=15)
        veri = r.json()
        if not isinstance(veri, list):
            return False, "Beklenmeyen yanıt (liste değil)."
        USAGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(UZAK_DOSYA, "w", encoding="utf-8") as f:
            for e in veri:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return True, f"{len(veri)} olay çekildi."
    except Exception as e:
        return False, f"Çekme başarısız: {e}"
