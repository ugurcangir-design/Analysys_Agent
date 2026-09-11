"""
Analiz veri kaynakları (Postgres/Jira MCP) — config → CLI argümanları testi (3.c-ii).
Gerçek analiz/MCP ÇALIŞTIRMAZ; yalnız üretilen config + args deterministik doğrulanır.
Çalıştır:  venv/bin/python tests/test_analiz_mcp.py
"""

import sys
import json
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import skills.analiz_mcp as am   # noqa: E402

_tmp = Path(tempfile.mkdtemp())
am.KONFIG_YOL = _tmp / "analiz_mcp.json"
am.URETILEN_YOL = _tmp / ".mcp-analiz.json"
am._npx_yolu_bul = lambda: "/usr/bin/npx"    # npx varmış gibi

ok = 0


def dogru(kosul, ad):
    global ok
    assert kosul, f"FAIL {ad}"
    ok += 1
    print(f"  ✓ {ad}")


# Varsayılan: kapalı → hiç argüman yok (davranış değişmez)
dogru(am.cli_argumanlari() == [], "varsayılan kapalı → args boş")
dogru(am.durum()["hazir_sunucular"] == [], "varsayılan: hazır sunucu yok")

# Postgres aktif
am.konfig_yaz({"postgres": {"aktif": True, "baglanti": "postgresql://ro:x@db/app"}, "jira": {}})
args = am.cli_argumanlari()
dogru("--mcp-config" in args and "--strict-mcp-config" in args, "pg: mcp-config + strict")
dogru("--allowedTools" in args and "mcp__postgres__query" in args, "pg: allowedTools postgres query")
cfg = json.loads(am.URETILEN_YOL.read_text())
dogru("postgres" in cfg["mcpServers"], "üretilen config: postgres sunucusu")
dogru("postgresql://ro:x@db/app" in cfg["mcpServers"]["postgres"]["args"], "bağlantı dizesi args'ta")

# Boş bağlantı ile 'kaydet' mevcut sırrı korumaz (bu test seviyesinde) → aktif ama baglanti boşsa sunucu yok
am.konfig_yaz({"postgres": {"aktif": True, "baglanti": ""}, "jira": {}})
dogru(am.cli_argumanlari() == [], "pg aktif ama bağlantı boş → args yok")

# Jira aktif
am.konfig_yaz({"postgres": {"aktif": False, "baglanti": ""},
               "jira": {"aktif": True, "komut": "npx", "args": ["-y", "jira-mcp"]}})
args = am.cli_argumanlari()
dogru("mcp__jira__jira_search" in args, "jira: allowedTools jira_search")
cfg = json.loads(am.URETILEN_YOL.read_text())
dogru(cfg["mcpServers"]["jira"]["args"] == ["-y", "jira-mcp"], "jira: komut args korunur")

# durum: bağlantı dizesi açıklanmaz
d = am.durum()
dogru("baglanti" not in json.dumps(d) and d["jira"]["aktif"], "durum sırrı sızdırmaz")

print(f"\nANALİZ MCP TESTLERİ GEÇTİ ({ok} kontrol)")
