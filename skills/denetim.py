"""
Denetim Kaydı (audit log) — v2 Faz 2.4.

Kim, ne yaptı, ne zaman: state değiştiren önemli aksiyonlar `logs/audit.jsonl`'e
append edilir. Kullanım telemetrisinden (skills/telemetri — iş hacmi/efor ölçümü)
AYRIDIR: bu kayıt yönetimsel izlenebilirlik içindir (giriş/çıkış, onay/ret,
yeniden üretim, güncelleme, kullanıcı/yetki değişiklikleri).

Deterministik, 0 token, fail-safe: yazım hatası uygulamayı asla etkilemez.
"""

import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
AUDIT_DOSYA = BASE_DIR / "logs" / "audit.jsonl"
VARSAYILAN_LIMIT = 200


def yaz(islem: str, hedef: str = "", detay: dict | None = None,
        kullanici: str | None = None, ip: str | None = None) -> None:
    """Bir denetim olayı ekler. `kullanici` None ise OS kullanıcısına düşer."""
    try:
        AUDIT_DOSYA.parent.mkdir(parents=True, exist_ok=True)
        kayit = {
            "zaman": datetime.now().isoformat(timespec="seconds"),
            "kullanici": kullanici or os.getenv("ANALIST") or os.getenv("USER") or "?",
            "islem": islem,
            "hedef": hedef,
            "detay": detay or {},
        }
        if ip:
            kayit["ip"] = ip
        with AUDIT_DOSYA.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except Exception:
        pass


def oku(limit: int = VARSAYILAN_LIMIT, islem: str | None = None,
        kullanici: str | None = None) -> list[dict]:
    """En yeni önce; isteğe bağlı işlem/kullanıcı filtresi."""
    if not AUDIT_DOSYA.exists():
        return []
    sonuc: list[dict] = []
    try:
        for satir in AUDIT_DOSYA.read_text(encoding="utf-8").splitlines():
            if not satir.strip():
                continue
            try:
                k = json.loads(satir)
            except Exception:
                continue
            if islem and k.get("islem") != islem:
                continue
            if kullanici and k.get("kullanici") != kullanici:
                continue
            sonuc.append(k)
    except Exception:
        return []
    sonuc.reverse()
    return sonuc[:max(1, min(limit, 2000))]


def islem_tipleri() -> list[str]:
    """Filtre menüsü için görülen işlem tipleri (sıralı, tekil)."""
    return sorted({k.get("islem", "") for k in oku(limit=2000)} - {""})
