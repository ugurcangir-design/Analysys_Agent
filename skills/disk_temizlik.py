"""
Disk Temizlik — makine dolmasına karşı zamanlanmış + elle temizlik (0 token, deterministik).

Ne temizlenir (yalnız YENİDEN ÜRETİLEBİLİR / arşiv nitelikli dosyalar — analiz çıktıları ASLA):
  - `.api_cache/*.txt`             → TTL'i geçmiş API/CLI yanıt önbelleği (base._API_CACHE_TTL, vars. 7 gün)
  - `reference/_filtered_cache/*`  → RAG filtre ara dosyaları (7 gün)
  - `reference/live-app/*`         → Chrome MCP gözlem çıktıları (30 gün)
  - `logs/*.log.N`, `logs/*.log`   → döndürülmüş/eskimiş log dosyaları (30 gün; son 24 saatte yazılan AKTİF log korunur)
  - `backlog/*.xlsx`               → UAT Mutabakat raporları (30 gün)
  - `history/<ts>/`                → önceki oturum arşivleri (60 gün; HISTORY_LIMIT zaten adet sınırlar)

DOKUNULMAZ: `output/` (aktif analiz), `input/` (girdi doküman), `reference/{confluence,jira,services}`,
`logs/usage/` (telemetri olayları), `.env`, `analist.json`, `kullanicilar.json`.

Zamanlama: app.py `_disk_temizlik_dongusu` — DISK_TEMIZLIK=true (vars.), DISK_TEMIZLIK_ARALIK sn (vars. 86400),
yalnız iş yokken (`_mesgul_mu()` None) çalışır. Durum `logs/disk-temizlik-durum.json`.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from skills.base import BASE_DIR

GUN = 86400
DURUM_DOSYA = BASE_DIR / "logs" / "disk-temizlik-durum.json"

# (dizin, glob, yaş eşiği-gün, dizin-mi)
_KURALLAR: list[tuple[Path, str, int, bool]] = [
    (BASE_DIR / ".api_cache",                  "*.txt",   7,  False),
    (BASE_DIR / "reference" / "_filtered_cache", "*",     7,  False),
    (BASE_DIR / "reference" / "live-app",      "*",       30, False),
    (BASE_DIR / "logs",                        "*.log.*", 30, False),
    (BASE_DIR / "logs",                        "*.log",   30, False),
    (BASE_DIR / "backlog",                     "*.xlsx",  30, False),
    (BASE_DIR / "history",                     "*",       60, True),
]
_AKTIF_LOG_KORUMA_SN = GUN   # son 24 saatte yazılan log aktif sayılır → silinmez


def _boyut(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _cache_ttl() -> int:
    try:
        from skills.base import _API_CACHE_TTL
        return int(_API_CACHE_TTL)
    except Exception:
        return 7 * GUN


def plan() -> dict:
    """Silinecek adayları listele (KURU ÇALIŞMA — hiçbir şey silinmez)."""
    simdi = time.time()
    adaylar: list[dict] = []
    for dizin, desen, yas_gun, dizin_mi in _KURALLAR:
        if not dizin.exists():
            continue
        esik = _cache_ttl() if dizin.name == ".api_cache" else yas_gun * GUN
        for p in dizin.glob(desen):
            if p.name.startswith(".") or p.is_symlink():
                continue
            if dizin_mi != p.is_dir():
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if dizin.name == "logs" and simdi - mtime < _AKTIF_LOG_KORUMA_SN:
                continue
            if simdi - mtime < esik:
                continue
            adaylar.append({
                "yol": str(p.relative_to(BASE_DIR)), "mb": round(_boyut(p) / 1_048_576, 2),
                "yas_gun": int((simdi - mtime) // GUN), "kural": f"{dizin.relative_to(BASE_DIR)}/{desen}",
            })
    toplam_mb = round(sum(a["mb"] for a in adaylar), 2)
    return {"adaylar": adaylar, "adet": len(adaylar), "toplam_mb": toplam_mb}


def uygula(tetik: str = "elle") -> dict:
    """Planı uygula; sonuç `DURUM_DOSYA`'ya yazılır ve döner."""
    p = plan()
    silinen, hata = 0, []
    for a in p["adaylar"]:
        yol = BASE_DIR / a["yol"]
        try:
            if yol.is_dir():
                shutil.rmtree(yol)
            else:
                yol.unlink()
            silinen += 1
        except Exception as e:  # tek dosya hatası tümünü durdurmasın
            hata.append(f"{a['yol']}: {e}")
    sonuc = {
        "zaman": time.time(), "tetik": tetik, "silinen": silinen,
        "kazanilan_mb": p["toplam_mb"], "hata": hata[:10],
    }
    _durum_yaz(sonuc)
    return sonuc


def _durum_yaz(sonuc: dict) -> None:
    try:
        DURUM_DOSYA.parent.mkdir(parents=True, exist_ok=True)
        DURUM_DOSYA.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def son_calisma() -> dict | None:
    try:
        return json.loads(DURUM_DOSYA.read_text(encoding="utf-8"))
    except Exception:
        return None


def dosya_sistemi() -> dict:
    """Uygulamanın bulunduğu birimin gerçek boş alanı (disk dolma uyarısı için)."""
    try:
        du = shutil.disk_usage(BASE_DIR)
        return {"toplam_gb": round(du.total / 1e9, 1), "bos_gb": round(du.free / 1e9, 1),
                "bos_yuzde": round(du.free / du.total * 100, 1)}
    except Exception:
        return {}


def zamanlama_ayarlari() -> dict:
    return {
        "aktif": os.getenv("DISK_TEMIZLIK", "true").lower() in ("1", "true", "yes"),
        "aralik_sn": max(3600, int(os.getenv("DISK_TEMIZLIK_ARALIK", str(GUN)) or GUN)),
    }
