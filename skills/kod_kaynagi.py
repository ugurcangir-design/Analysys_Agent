"""
Kod Kaynağı soyutlaması — v2 Faz 3 · Artım 3a (bkz. docs/ROADMAP-V2.md Faz 3).

Analizi gerçek uygulama koduna bağlamanın ALTYAPISI. Yol haritası kararı: gerçek
repo bağlantısı ŞİMDİ zorunlu değil — arayüz HAZIR kurulur, repo yapılandırılınca
dolar. Bu modül, kod kaynağına (yerel git/dosya sistemi) SALT-OKUMA, yol-güvenli,
deterministik (0 token) bir arayüz sağlar; MCP dosya/git ya da uzak repo adaptörleri
sonradan aynı arayüzü uygular.

Yapılandırma makineye özeldir: `reference/kod_kaynagi.json` (gitignore; `.example`
seed edilir) — her analistin kendi checkout yolu farklı olabilir.

Güvenlik: tüm yollar repo köküne HAPSEDİLİR (resolve + is_relative_to); ikili/çok
büyük dosyalar atlanır; tarama sayı/süre sınırlıdır. Yazma YOK, komut çalıştırma YOK
(yalnız `git` salt-okuma alt komutları).
"""

import shutil
import subprocess
import json
from pathlib import Path

from .base import REF_DIR

KONFIG_YOL = REF_DIR / "kod_kaynagi.json"

# Taranmayacak dizinler (gürültü + performans)
_HARIC_DIZIN = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
                ".next", ".cache", "coverage", ".idea", ".vscode", "vendor", ".mypy_cache",
                ".ruff_cache", ".pytest_cache", "site-packages"}
# Kaynak kodu sayılan uzantılar (dil tespiti + arama odağı)
_KOD_UZANTI = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rb": "Ruby",
    ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".c": "C", ".rs": "Rust", ".sql": "SQL",
    ".vue": "Vue", ".swift": "Swift", ".scala": "Scala", ".sh": "Shell",
}
_METIN_UZANTI = _KOD_UZANTI.keys() | {".md", ".txt", ".json", ".yaml", ".yml", ".xml",
                                      ".html", ".css", ".scss", ".toml", ".ini", ".env.example"}

MAX_DOSYA_BAYT = 512_000        # tek dosya okuma üst sınırı
MAX_ARAMA_DOSYA = 4000          # python fallback taramasında en fazla dosya
MAX_ARAMA_SONUC = 200           # en fazla eşleşme
GIT_TIMEOUT = 15


# ─── Yapılandırma ─────────────────────────────────────────────────────────────

def konfig_oku() -> dict:
    if KONFIG_YOL.exists():
        try:
            return json.loads(KONFIG_YOL.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"repolar": []}


def konfig_yaz(repolar: list[dict]) -> None:
    """repolar: [{ad, yol, aktif}]. Atomik yazım."""
    temiz = []
    for r in repolar:
        ad = (r.get("ad") or "").strip()
        yol = (r.get("yol") or "").strip()
        if ad and yol:
            temiz.append({"ad": ad, "yol": yol, "aktif": bool(r.get("aktif", True))})
    KONFIG_YOL.parent.mkdir(parents=True, exist_ok=True)
    tmp = KONFIG_YOL.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"repolar": temiz}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(KONFIG_YOL)


def _repo_kok(ad: str) -> Path | None:
    """Yapılandırılmış repo adının kök yolu (var olan bir dizinse)."""
    for r in konfig_oku().get("repolar", []):
        if r.get("ad") == ad and r.get("yol"):
            k = Path(r["yol"]).expanduser()
            if k.is_dir():
                return k.resolve()
    return None


def _guvenli_yol(kok: Path, alt: str) -> Path | None:
    """alt yolunu repo köküne hapseder. Kaçış girişimi → None."""
    try:
        hedef = (kok / (alt or "")).resolve()
    except Exception:
        return None
    if hedef == kok or kok in hedef.parents:
        return hedef
    return None


def _git(kok: Path, args: list[str]) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=str(kok), capture_output=True,
                           text=True, timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


# ─── Durum ────────────────────────────────────────────────────────────────────

def yapilandirildi_mi() -> bool:
    return any(_repo_kok(r["ad"]) for r in konfig_oku().get("repolar", []) if r.get("aktif", True))


def repolar() -> list[dict]:
    """Yapılandırılmış repolar + durum (var mı, git mi, branch, dosya/dil özeti)."""
    sonuc = []
    for r in konfig_oku().get("repolar", []):
        ad = r.get("ad", "")
        kok = _repo_kok(ad)
        durum = {"ad": ad, "yol": r.get("yol", ""), "aktif": bool(r.get("aktif", True)),
                 "var": kok is not None, "git": False, "branch": None, "commit": None,
                 "dosya": 0, "diller": {}}
        if kok:
            durum["git"] = (kok / ".git").exists()
            if durum["git"]:
                durum["branch"] = _git(kok, ["rev-parse", "--abbrev-ref", "HEAD"])
                durum["commit"] = _git(kok, ["log", "-1", "--pretty=format:%h %s"])
            diller: dict[str, int] = {}
            adet = 0
            for p in _dosyalari_gez(kok):
                adet += 1
                dil = _KOD_UZANTI.get(p.suffix.lower())
                if dil:
                    diller[dil] = diller.get(dil, 0) + 1
                if adet >= MAX_ARAMA_DOSYA:
                    break
            durum["dosya"] = adet
            durum["diller"] = dict(sorted(diller.items(), key=lambda x: -x[1])[:8])
        sonuc.append(durum)
    return sonuc


def _dosyalari_gez(kok: Path):
    """Repo altındaki metin/kod dosyalarını üretir (harici dizinleri atlar)."""
    yigin = [kok]
    while yigin:
        d = yigin.pop()
        try:
            for p in d.iterdir():
                if p.is_symlink():
                    continue
                if p.is_dir():
                    if p.name not in _HARIC_DIZIN:
                        yigin.append(p)
                elif p.suffix.lower() in _METIN_UZANTI:
                    yield p
        except (PermissionError, OSError):
            continue


# ─── Dosya ağacı / okuma ──────────────────────────────────────────────────────

def dosya_agaci(ad: str, alt_yol: str = "", limit: int = 300) -> dict:
    """Bir dizinin doğrudan içeriği (tek seviye): klasörler + dosyalar."""
    kok = _repo_kok(ad)
    if not kok:
        return {"ok": False, "error": "Repo yapılandırılmadı veya yol yok"}
    hedef = _guvenli_yol(kok, alt_yol)
    if not hedef or not hedef.exists():
        return {"ok": False, "error": "Yol bulunamadı"}
    if hedef.is_file():
        return {"ok": False, "error": "Yol bir dosya (dosya_oku kullanın)"}
    klasorler, dosyalar = [], []
    try:
        for p in sorted(hedef.iterdir(), key=lambda x: x.name.lower()):
            if p.is_symlink():
                continue
            rel = str(p.relative_to(kok))
            if p.is_dir():
                if p.name not in _HARIC_DIZIN:
                    klasorler.append({"ad": p.name, "yol": rel})
            elif p.suffix.lower() in _METIN_UZANTI:
                dosyalar.append({"ad": p.name, "yol": rel, "boyut": p.stat().st_size,
                                 "dil": _KOD_UZANTI.get(p.suffix.lower())})
            if len(klasorler) + len(dosyalar) >= limit:
                break
    except (PermissionError, OSError) as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "yol": str(hedef.relative_to(kok)) if hedef != kok else "",
            "klasorler": klasorler, "dosyalar": dosyalar}


def dosya_oku(ad: str, yol: str, limit: int = MAX_DOSYA_BAYT) -> dict:
    """Repo içindeki bir dosyayı SALT-OKUMA döndürür (yol-güvenli, boyut sınırlı)."""
    kok = _repo_kok(ad)
    if not kok:
        return {"ok": False, "error": "Repo yapılandırılmadı"}
    hedef = _guvenli_yol(kok, yol)
    if not hedef or not hedef.is_file():
        return {"ok": False, "error": "Dosya bulunamadı"}
    if hedef.suffix.lower() not in _METIN_UZANTI:
        return {"ok": False, "error": "Metin/kod dosyası değil"}
    boyut = hedef.stat().st_size
    try:
        icerik = hedef.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "yol": yol, "dil": _KOD_UZANTI.get(hedef.suffix.lower()),
            "boyut": boyut, "kesildi": boyut > limit, "icerik": icerik}


# ─── Arama ────────────────────────────────────────────────────────────────────

def ara(ad: str, sorgu: str, limit: int = MAX_ARAMA_SONUC) -> dict:
    """Repo genelinde metin araması (ripgrep varsa onunla, yoksa python).
    Dönen: [{yol, satir_no, satir}]. Salt-okuma."""
    kok = _repo_kok(ad)
    if not kok:
        return {"ok": False, "error": "Repo yapılandırılmadı"}
    sorgu = (sorgu or "").strip()
    if len(sorgu) < 2:
        return {"ok": False, "error": "Arama en az 2 karakter olmalı"}

    rg = shutil.which("rg")
    eslesme = []
    rg_calisti = False   # ripgrep KURULU olsa da exception atarsa fallback yine çalışmalı
    if rg:
        try:
            args = [rg, "--line-number", "--no-heading", "--color", "never",
                    "--max-count", "5", "--max-columns", "300", "-i",
                    "--fixed-strings", sorgu]
            for d in _HARIC_DIZIN:
                args += ["--glob", f"!{d}/"]
            r = subprocess.run(args, cwd=str(kok), capture_output=True, text=True,
                               timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace")
            for satir in r.stdout.splitlines()[:limit]:
                p = satir.split(":", 2)
                if len(p) == 3:
                    eslesme.append({"yol": p[0], "satir_no": int(p[1]) if p[1].isdigit() else 0,
                                    "satir": p[2].strip()[:300]})
            rg_calisti = True
        except Exception:
            eslesme = []
    if not eslesme and not rg_calisti:
        alt = sorgu.lower()
        taranan = 0
        for p in _dosyalari_gez(kok):
            taranan += 1
            if taranan > MAX_ARAMA_DOSYA or len(eslesme) >= limit:
                break
            try:
                if p.stat().st_size > MAX_DOSYA_BAYT:
                    continue
                for i, satir in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if alt in satir.lower():
                        eslesme.append({"yol": str(p.relative_to(kok)), "satir_no": i,
                                        "satir": satir.strip()[:300]})
                        if len(eslesme) >= limit:
                            break
            except Exception:
                continue
    return {"ok": True, "sorgu": sorgu, "motor": "ripgrep" if rg else "python",
            "adet": len(eslesme), "eslesmeler": eslesme}


def git_gecmis(ad: str, yol: str, limit: int = 10) -> dict:
    """Bir yola dokunan son commit'ler (etki/kaynak izi). Salt-okuma."""
    kok = _repo_kok(ad)
    if not kok or not (kok / ".git").exists():
        return {"ok": False, "error": "Git deposu değil"}
    hedef = _guvenli_yol(kok, yol)
    if not hedef:
        return {"ok": False, "error": "Yol bulunamadı"}
    cikti = _git(kok, ["log", f"-{max(1, min(limit, 50))}", "--pretty=format:%h|%an|%ci|%s", "--", yol])
    if cikti is None:
        return {"ok": False, "error": "git log başarısız"}
    commits = []
    for satir in cikti.splitlines():
        p = satir.split("|", 3)
        if len(p) == 4:
            commits.append({"hash": p[0], "yazar": p[1], "tarih": p[2][:19], "mesaj": p[3]})
    return {"ok": True, "yol": yol, "commits": commits}
