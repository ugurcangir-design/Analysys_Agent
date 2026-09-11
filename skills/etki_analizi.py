"""
Etki Analizi iskeleti — v2 Faz 3 · Artım 3.b (bkz. docs/ROADMAP-V2.md Faz 3).

Bir analiz çıktısındaki teknik VARLIKLARI (backtick'li kod terimleri, DB alan/tablo
adları, endpoint yolları) deterministik olarak çıkarır; kod kaynağı (3.a) bağlıysa
her varlığı repo'da arar → "bu değişiklik hangi dosya/satırları etkiler" iskeleti.
Repo bağlı DEĞİLSE yalnız varlık listesi döner (bağlanınca dolar).

0 token, AI YOK — parse + grep. Amaç kesin liste değil, analiste ETKİ HARİTASI
başlangıcı sunmak; sonuçlar analistin doğrulaması içindir.
"""

import re

from . import kod_kaynagi
from .base import OUTPUT_DIR

# Backtick içi teknik terim: `getWallet`, `refund_amount`, `/api/x`, `wallets`
_BACKTICK = re.compile(r"`([^`\n]{2,60})`")
# Endpoint / yol
_ENDPOINT = re.compile(r"\b((?:GET|POST|PUT|PATCH|DELETE)\s+)?(/[a-zA-Z0-9_\-/{}:]{2,60})")
# Kod-benzeri tanımlayıcı: camelCase, snake_case, PascalCase (en az bir iç sınır)
_IDENT = re.compile(r"\b([a-zA-Z][a-zA-Z0-9]*(?:[_][a-zA-Z0-9]+)+|[a-z]+[A-Z][a-zA-Z0-9]*|[A-Z][a-z]+[A-Z][a-zA-Z0-9]*)\b")

# Aranmayacak yaygın/gürültü terimler (analiz jargonu + genel)
_STOP = {
    "surec_analizi", "teknik_analiz", "brd_analizi", "kapsam_analizi", "acik_sorular",
    "ProcessID", "requestId", "true", "false", "null", "None", "TODO", "README",
    "JavaScript", "TypeScript", "PostgreSQL", "getElementById", "querySelector",
}
# Yapısal ID'ler (koda gitmez ama izlenir): PA-/BR-/AC-/EK-/Q-/T-
_YAPISAL = re.compile(r"\b((?:PA|BR|AC|EK|Q|Q-T|Q-K|T|PO)-[A-Z]?-?\d+)\b")

MAX_VARLIK = 40          # aranacak en fazla varlık
MAX_ISABET = 6           # varlık başına en fazla kod isabeti


def varliklari_cikar(metin: str) -> dict:
    """Metinden tipli varlıklar çıkarır: kod terimleri, endpoint'ler, yapısal ID'ler."""
    kod: dict[str, int] = {}
    endpoint: set[str] = set()
    yapisal: set[str] = set()

    for m in _BACKTICK.finditer(metin):
        t = m.group(1).strip()
        if t.startswith("/"):
            endpoint.add(t)
        elif _IDENT.fullmatch(t) and t not in _STOP:
            kod[t] = kod.get(t, 0) + 3          # backtick = yüksek sinyal
        elif re.fullmatch(r"[a-z][a-z0-9_]{2,40}", t) and "_" in t and t not in _STOP:
            kod[t] = kod.get(t, 0) + 3

    for m in _ENDPOINT.finditer(metin):
        yol = m.group(2)
        if yol.count("/") >= 1 and len(yol) >= 4:
            endpoint.add(yol)

    for m in _IDENT.finditer(metin):
        t = m.group(1)
        if t not in _STOP and len(t) >= 4:
            kod[t] = kod.get(t, 0) + 1

    for m in _YAPISAL.finditer(metin):
        yapisal.add(m.group(1))

    # Sinyale göre sırala, kap
    kod_sirali = [k for k, _ in sorted(kod.items(), key=lambda x: (-x[1], x[0]))][:MAX_VARLIK]
    return {
        "kod": kod_sirali,
        "endpoint": sorted(endpoint)[:MAX_VARLIK],
        "yapisal": sorted(yapisal),
    }


def analiz(dosya_adi: str, repo: str | None = None) -> dict:
    """Bir çıktı dosyasının etki analizini üretir.

    repo verilir ve yapılandırılmışsa her kod-varlığı/endpoint kod kaynağında aranır.
    Dönen: {varlik_sayisi, repo, kod_bagli, etkiler:[{varlik,tip,isabet:[...],commit}], yapisal:[...]}
    """
    yol = OUTPUT_DIR / dosya_adi
    if not yol.exists():
        return {"ok": False, "error": "Çıktı dosyası yok"}
    metin = yol.read_text(encoding="utf-8", errors="replace")
    v = varliklari_cikar(metin)

    kod_bagli = bool(repo) and kod_kaynagi._repo_kok(repo) is not None
    etkiler = []
    if kod_bagli:
        for tip, liste in (("kod", v["kod"]), ("endpoint", v["endpoint"])):
            for varlik in liste:
                sonuc = kod_kaynagi.ara(repo, varlik, limit=MAX_ISABET)
                isabet = sonuc.get("eslesmeler", []) if sonuc.get("ok") else []
                if isabet:
                    etkiler.append({
                        "varlik": varlik, "tip": tip, "adet": len(isabet),
                        "isabet": isabet,
                        "dosyalar": sorted({e["yol"] for e in isabet}),
                    })
        # En çok dosyaya dokunanlar önce
        etkiler.sort(key=lambda e: -len(e["dosyalar"]))

    return {
        "ok": True,
        "dosya": dosya_adi,
        "repo": repo,
        "kod_bagli": kod_bagli,
        "varlik_sayisi": len(v["kod"]) + len(v["endpoint"]),
        "varliklar": v,
        "etkiler": etkiler,
        "etkilenen_dosyalar": sorted({d for e in etkiler for d in e["dosyalar"]}),
    }
