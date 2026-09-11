"""
Analiz Veri Kaynakları (Postgres/Jira MCP) — v2 Faz 3 · Artım 3.c-ii.

Analizi gerçek veriye bağlamanın ALTYAPISI: `claude -p`'ye Postgres/Jira MCP sunucusu
+ salt-okuma araç izni (`--allowedTools`) geçme. Canlı-app Chrome MCP deseninin
(base._live_app_cli_argumanlari) veri-kaynağı muadili.

Yol haritası kararı: KURULUR, otomatik çalıştırılmaz — varsayılan KAPALI. Owner
yapılandırıp aktif edince analiz çağrılarına MCP eklenir; aksi halde hiçbir ek
argüman gitmez (davranış değişmez). Gerçek analiz provası kota + canlı DB/Jira
gerektirir → analistin işi.

Config makineye özel: `reference/analiz_mcp.json` (gitignore; `.example` seed).
Üretilen `.mcp-analiz.json` bağlantı dizesi içerir → o da gitignore.
"""

import json
from pathlib import Path

from .base import REF_DIR, BASE_DIR, _npx_yolu_bul

KONFIG_YOL = REF_DIR / "analiz_mcp.json"
URETILEN_YOL = BASE_DIR / ".mcp-analiz.json"

# İzin verilen araçlar — SALT-OKUMA odaklı (analiz için sorgu/okuma yeter).
POSTGRES_ARACLAR = ["mcp__postgres__query"]
JIRA_ARACLAR = ["mcp__jira__jira_search", "mcp__jira__jira_get_issue"]
POSTGRES_PAKET = "@modelcontextprotocol/server-postgres"


def _varsayilan() -> dict:
    return {
        "postgres": {"aktif": False, "baglanti": ""},
        "jira": {"aktif": False, "komut": "", "args": []},
    }


def konfig_oku() -> dict:
    if KONFIG_YOL.exists():
        try:
            v = json.loads(KONFIG_YOL.read_text(encoding="utf-8"))
            temel = _varsayilan()
            temel.update({k: v[k] for k in ("postgres", "jira") if k in v})
            return temel
        except Exception:
            pass
    return _varsayilan()


def konfig_yaz(veri: dict) -> None:
    """Yalnız bilinen alanları temizleyip yazar (atomik)."""
    pg = veri.get("postgres") or {}
    jira = veri.get("jira") or {}
    temiz = {
        "postgres": {"aktif": bool(pg.get("aktif")), "baglanti": (pg.get("baglanti") or "").strip()},
        "jira": {"aktif": bool(jira.get("aktif")), "komut": (jira.get("komut") or "").strip(),
                 "args": [str(a) for a in (jira.get("args") or []) if str(a).strip()]},
    }
    KONFIG_YOL.parent.mkdir(parents=True, exist_ok=True)
    tmp = KONFIG_YOL.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(temiz, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(KONFIG_YOL)


def _aktif_sunucular() -> tuple[dict, list[str]]:
    """Aktif + geçerli MCP sunucu tanımları ve izinli araç listesi."""
    cfg = konfig_oku()
    sunucular: dict = {}
    araclar: list[str] = []
    pg = cfg.get("postgres", {})
    if pg.get("aktif") and pg.get("baglanti"):
        npx = _npx_yolu_bul()
        if npx:
            sunucular["postgres"] = {"command": npx, "args": ["-y", POSTGRES_PAKET, pg["baglanti"]]}
            araclar += POSTGRES_ARACLAR
    jira = cfg.get("jira", {})
    if jira.get("aktif") and jira.get("komut"):
        sunucular["jira"] = {"command": jira["komut"], "args": list(jira.get("args", []))}
        araclar += JIRA_ARACLAR
    return sunucular, araclar


def mcp_config_yaz() -> tuple[Path | None, list[str]]:
    """Aktif sunucularla `.mcp-analiz.json` üretir. Yoksa (None, [])."""
    sunucular, araclar = _aktif_sunucular()
    if not sunucular:
        return None, []
    URETILEN_YOL.write_text(json.dumps({"mcpServers": sunucular}, indent=2), encoding="utf-8")
    return URETILEN_YOL, araclar


def cli_argumanlari() -> list[str]:
    """`claude -p`'ye eklenecek MCP argümanları. Yapılandırılmamışsa boş liste."""
    cfg, araclar = mcp_config_yaz()
    if not cfg:
        return []
    return ["--mcp-config", str(cfg), "--strict-mcp-config", "--allowedTools", *araclar]


def durum() -> dict:
    """UI/sağlık için özet (bağlantı dizesi/kimlik AÇIKLANMAZ — yalnız aktiflik)."""
    cfg = konfig_oku()
    sunucular, araclar = _aktif_sunucular()
    pg = cfg.get("postgres", {})
    jira = cfg.get("jira", {})
    return {
        "postgres": {"aktif": bool(pg.get("aktif")), "yapili": bool(pg.get("baglanti"))},
        "jira": {"aktif": bool(jira.get("aktif")), "yapili": bool(jira.get("komut"))},
        "hazir_sunucular": sorted(sunucular.keys()),
        "arac_sayisi": len(araclar),
        "npx": bool(_npx_yolu_bul()),
    }
