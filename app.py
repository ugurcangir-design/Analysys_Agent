"""
Flask web sunucusu — Analyst Studio (port 5002)
"""

import os
import re
import sys
import json
import time
import signal
import shutil
import logging
import logging.handlers
import secrets
import zipfile
import subprocess
import threading
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, abort, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from skills.atlassian import (
    env_oku as _env_oku,
    atlassian_get as _atlassian_get,
    atlassian_post as _atlassian_post,
)

load_dotenv()

BASE_DIR   = Path(__file__).parent
INPUT_DIR  = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
REF_DIR    = BASE_DIR / "reference"
HISTORY_DIR = BASE_DIR / "history"
LOG_DIR    = BASE_DIR / "logs"

UI_CODE_DIR  = REF_DIR / "ui-code"
CONF_DIR     = REF_DIR / "confluence"
JIRA_REF_DIR = REF_DIR / "jira"
SERVIS_DIR   = REF_DIR / "services"

for d in [INPUT_DIR, OUTPUT_DIR, REF_DIR / "current-brd", UI_CODE_DIR,
          CONF_DIR, JIRA_REF_DIR, SERVIS_DIR, HISTORY_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "app.log"
_log_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[_log_handler, logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _eski_loglari_temizle(gun: int = 30) -> None:
    """Tarih bazlı eski app-YYYYMMDD.log dosyalarını sil (rotation öncesinden kalanlar)."""
    import re as _re
    esik = time.time() - gun * 86400
    desen = _re.compile(r"^app-\d{8}\.log$")
    silinen = 0
    for f in LOG_DIR.iterdir():
        if not f.is_file() or not desen.match(f.name):
            continue
        try:
            if f.stat().st_mtime < esik:
                f.unlink()
                silinen += 1
        except OSError:
            pass
    if silinen:
        logger.info(f"{silinen} eski log dosyası temizlendi (>{gun} gün).")


_eski_loglari_temizle()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Yerel HTTP'de Secure=True cookie'yi gönderilmez yapar; HTTPS gerektiğinde env ile aç
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

# SECRET_KEY: .env'den alınır, yoksa kalıcı olarak üretilip .env'e kaydedilir
_sk = os.getenv("SECRET_KEY")
if not _sk:
    _sk = secrets.token_hex(32)
    _env_yolu_sk = Path(__file__).parent / ".env"
    with open(_env_yolu_sk, "a", encoding="utf-8") as _f:
        _f.write(f"\nSECRET_KEY={_sk}\n")
    try:
        os.chmod(_env_yolu_sk, 0o600)
    except OSError:
        pass
app.secret_key = _sk

# Kullanıcı veritabanı — root dizinde, git'e gitmez
USERS_PATH = BASE_DIR / "users.json"

# Auth gerektirmeyen route'lar
AUTH_MUAF = {"/login", "/api/auth/login"}


# ─── Brute-force Koruması ────────────────────────────────────────────────────

_login_denemeler: dict[str, list[float]] = defaultdict(list)
_LOGIN_LIMIT   = 5   # maksimum başarısız deneme
_LOGIN_PENCERE = 60  # saniye içinde


def _brute_force_kontrol(ip: str) -> bool:
    """True dönerse o IP'yi engelle."""
    simdi = time.time()
    denemeler = [t for t in _login_denemeler[ip] if simdi - t < _LOGIN_PENCERE]
    _login_denemeler[ip] = denemeler
    return len(denemeler) >= _LOGIN_LIMIT


def _basarisiz_giris_kaydet(ip: str) -> None:
    _login_denemeler[ip].append(time.time())


def _kullanicilari_oku() -> dict:
    if not USERS_PATH.exists():
        return {}
    try:
        return json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _kullanicilari_yaz(users: dict) -> None:
    USERS_PATH.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def _giris_yapildi_mi() -> bool:
    return bool(session.get("username"))


def _admin_mi() -> bool:
    admin = os.getenv("ADMIN_USER", "").strip().lower()
    return bool(admin and session.get("username") == admin)


def admin_gerekli(fn):
    """Hassas admin endpoint'leri için decorator.

    Mantık:
    - AUTH kapalıysa (kişisel masaüstü kullanımı): geç — tek kullanıcı
      herkes admindir
    - AUTH açıksa: _admin_mi() true olmalı, yoksa 403
    """
    from functools import wraps

    @wraps(fn)
    def _sarici(*args, **kwargs):
        if _auth_aktif_mi() and not _admin_mi():
            logger.warning("Admin yetkisi yok: path=%s user=%s", request.path, session.get("username"))
            return jsonify({"error": "Admin yetkisi gerekli"}), 403
        return fn(*args, **kwargs)

    return _sarici


def _auth_aktif_mi() -> bool:
    return os.getenv("AUTH_ENABLED", "false").lower() in ("1", "true", "yes")


@app.before_request
def auth_kontrol():
    if not _auth_aktif_mi():
        return None
    if request.path in AUTH_MUAF:
        return None
    if request.path.startswith("/static/"):
        return None
    if not _giris_yapildi_mi():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Oturum açmanız gerekiyor", "auth_required": True}), 401
        return redirect(url_for("login_sayfasi"))


# ─── CSRF Koruması — Origin/Referer Kontrolü ────────────────────────────────
# SameSite=Lax cookie zaten cross-site POST'larda çerez göndermez (modern
# tarayıcılarda). Bu kontrol sunucu tarafında ek koruma — belt and suspenders.
# Yalnız state-değiştiren metotlarda (POST/PUT/PATCH/DELETE) çalışır.

# Tarayıcı dışı entegrasyonlardan gelen güvenli istisnalar.
# (örn. OAuth callback Atlassian'dan POST geri dönmez — GET'tir; ama yine de muaf)
CSRF_MUAF = {
    "/api/auth/login",   # login sırasında henüz session yok, Origin doğru zaten
    "/api/heartbeat",    # navigator.sendBeacon kullanılmıyor ama hızlı çağrı, gereksiz yere zorlama
}


@app.before_request
def csrf_kontrol():
    """State-değiştiren isteklerin same-origin'den geldiğini doğrular.

    Cross-site bir sayfa, kullanıcı login iken POST atmaya çalışırsa
    Origin/Referer header'ı kendi domain'i olur — engelleriz.
    """
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    if request.path in CSRF_MUAF:
        return None
    if request.path.startswith("/static/"):
        return None

    origin = request.headers.get("Origin", "")
    referer = request.headers.get("Referer", "")
    host_url = request.host_url.rstrip("/")  # örn. http://localhost:5002

    # Origin varsa öncelik onda; yoksa Referer'a bak
    kaynak = origin or referer
    if not kaynak:
        # Origin/Referer yoksa cross-site fetch olabilir — reddet
        return jsonify({"error": "Cross-origin isteği reddedildi (Origin/Referer yok)"}), 403

    # Kaynak host_url ile başlamalı (same-origin)
    if not kaynak.startswith(host_url):
        logger.warning(
            "CSRF reddi: path=%s origin=%s referer=%s host=%s",
            request.path, origin, referer, host_url
        )
        return jsonify({"error": "Cross-origin isteği reddedildi"}), 403

IZIN_VERILEN_UZANTILAR = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md", ".webp", ".docx"}
UI_UZANTILAR = {
    ".tsx", ".jsx", ".ts", ".js", ".mjs", ".cjs",
    ".vue", ".svelte",
    ".html", ".css", ".scss", ".less",
    ".yml", ".yaml", ".json",
}

# Zip extraction sırasında atlanacak klasörler
ZIP_ATLA_KLASORLER = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".next", ".nuxt", "coverage", ".cache", ".vite", "out",
    ".turbo", ".vercel", "storybook-static",
}
ZIP_MAX_DOSYA_BOYUTU = 512 * 1024       # 512 KB tek dosya
ZIP_MAX_TOPLAM_BOYUT = 50 * 1024 * 1024  # 50 MB toplam unzipped
IZIN_VERILEN_CIKTILAR = {
    "surec-analizi.md",
    "teknik-analiz.md",
    "acik-sorular.md",
    "brd-analizi.md",
    "brd-sorular.md",
    "kapsam-analizi.md",
    "alternatif-surecler.md",
    "jira-sonuc.txt",
    "mockup.html",
    "sorular.json",
}

# Referans kategorileri ve izin verilen uzantılar
REFERANS_KATEGORILER = {
    "confluence": {".md", ".txt", ".html", ".pdf"},
    "jira":       {".json"},
    "services":   {".json", ".yaml", ".yml"},
}
REFERANS_DIZINLER = {
    "confluence": None,  # app init'te set edilecek
    "jira":       None,
    "services":   None,
}
HISTORY_LIMIT = 5

REFERANS_DIZINLER["confluence"] = CONF_DIR
REFERANS_DIZINLER["jira"]       = JIRA_REF_DIR
REFERANS_DIZINLER["services"]   = SERVIS_DIR

# Sources (Veri Kaynakları) — Confluence spaces + Jira projeleri listesi
SOURCES_PATH = REF_DIR / "sources.json"
_sync_state: dict = {"running": False, "log": [], "last_sync": None, "error": None}
_sync_lock = threading.Lock()


def _load_sources() -> dict:
    if SOURCES_PATH.exists():
        try:
            return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"confluence_spaces": [], "jira_projects": [], "last_sync": None}


def _save_sources(data: dict) -> None:
    SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _html_to_text(html_str: str) -> str:
    import html as _html
    text = re.sub(r"<[^>]+>", " ", html_str)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _adf_to_text(node) -> str:
    if not node or not isinstance(node, dict):
        return ""
    parts = []
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
    for child in node.get("content", []):
        parts.append(_adf_to_text(child))
    return " ".join(p for p in parts if p)


def _fetch_confluence_space(space_key: str, cloud_id: str) -> int:
    """
    v2 API kullanır — granular scope (read:space:confluence, read:page:confluence) gerektirir.
    Modern Mode Confluence için v1 API kaldırıldı.
    """
    out_dir = CONF_DIR / space_key
    out_dir.mkdir(parents=True, exist_ok=True)
    spaces_data = _atlassian_get(
        f"/wiki/api/v2/spaces?keys={space_key}&limit=1",
        cloud_id=cloud_id, service="confluence"
    )
    results = spaces_data.get("results", [])
    if not results:
        raise Exception(f"Space bulunamadı: {space_key}")
    space_id = results[0]["id"]

    cursor, total = None, 0
    while True:
        cp = f"&cursor={cursor}" if cursor else ""
        data = _atlassian_get(
            f"/wiki/api/v2/pages?space-id={space_id}&limit=50&body-format=storage{cp}",
            cloud_id=cloud_id, service="confluence"
        )
        pages = data.get("results", [])
        if not pages:
            break
        for page in pages:
            title = page.get("title", "untitled")
            body_storage = (page.get("body") or {}).get("storage", {}).get("value", "")
            text = _html_to_text(body_storage) if body_storage else ""
            safe = re.sub(r"[^\w\s\-]", "", title)[:80].strip()
            safe = re.sub(r"\s+", "-", safe) or "page"
            (out_dir / f"{safe}.md").write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
            total += 1
        next_link = data.get("_links", {}).get("next", "")
        if not next_link:
            break
        cursor = next_link.split("cursor=")[-1].split("&")[0] if "cursor=" in next_link else None
        if not cursor:
            break
    return total


# Jira referans senkronizasyonunda DIŞLANACAK task statüleri.
# Bu statüler henüz işlenmemiş (Backlog/To Do) veya iptal edilmiş (Cancel)
# işleri temsil eder — analize bağlam olarak değer katmaz, hatta yanıltabilir.
# Dahil edilenler: In Progress, In Review, Done ve diğer "çalışılmış" statüler.
# Karşılaştırma normalize edilir (küçük harf, Türkçe karakter sadeleştirme),
# İngilizce + Türkçe varyantları kapsar.
JIRA_HARIC_STATUSLER = {
    "backlog",
    "to do", "todo", "yapilacak", "yapilacaklar", "acik", "open",
    "cancel", "cancelled", "canceled", "iptal", "iptal edildi", "iptal edilen",
}


def _status_normalize(status: str) -> str:
    """Status ismini karşılaştırma için normalize eder (küçük harf, TR→ASCII).

    Türkçe İ/I/ı, lower()'dan ÖNCE 'i'ye çevrilir — aksi halde Python'da
    'İ'.lower() birleşik nokta ('i̇') üretir ve eşleşme bozulur.
    """
    n = status.strip().replace("İ", "i").replace("I", "i").replace("ı", "i")
    n = n.lower().replace("-", " ").replace("_", " ")
    n = " ".join(n.split())  # çoklu boşluğu teke indir
    cevrim = str.maketrans("şğüöç", "sguoc")
    return n.translate(cevrim)


def _jira_status_haric_mi(status: str) -> bool:
    """True → bu status'teki task referans olarak KULLANILMAZ (Backlog/To Do/Cancel)."""
    return _status_normalize(status) in JIRA_HARIC_STATUSLER


def _fetch_jira_project(project_key: str, cloud_id: str) -> int:
    JIRA_REF_DIR.mkdir(parents=True, exist_ok=True)
    issues, next_token = [], None
    elenen = 0
    while True:
        body = {
            "jql": f"project={project_key} ORDER BY updated DESC",
            "fields": ["summary", "description", "status", "issuetype", "priority", "assignee"],
            "maxResults": 100,
        }
        if next_token:
            body["nextPageToken"] = next_token
        data = _atlassian_post("/rest/api/3/search/jql", body=body, cloud_id=cloud_id)
        batch = data.get("issues", [])
        if not batch:
            break
        for issue in batch:
            f = issue.get("fields", {})
            status_adi = (f.get("status") or {}).get("name", "")
            # Backlog / To Do / Cancel statüleri analize dahil edilmez
            if _jira_status_haric_mi(status_adi):
                elenen += 1
                continue
            desc = f.get("description") or ""
            if isinstance(desc, dict):
                desc = _adf_to_text(desc)
            issues.append({
                "key": issue["key"],
                "summary": f.get("summary", ""),
                "status": status_adi,
                "type": (f.get("issuetype") or {}).get("name", ""),
                "priority": (f.get("priority") or {}).get("name", ""),
                "assignee": (f.get("assignee") or {}).get("displayName", ""),
                "description": str(desc)[:500],
            })
        next_token = data.get("nextPageToken")
        if not next_token:
            break
    (JIRA_REF_DIR / f"{project_key}.json").write_text(
        json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if elenen:
        logger.info("Jira [%s]: %d task dahil, %d task elendi (Backlog/To Do/Cancel)",
                    project_key, len(issues), elenen)
    return len(issues), elenen


# Rerun (yeniden çalıştırma) lock — eş zamanlı rerun isteğini engeller
_rerun_lock = threading.Lock()

# Heartbeat takibi
_son_heartbeat = time.time()
_heartbeat_lock = threading.Lock()
_suspended = False          # True → tarayıcı 2+ dakikadır bağlı değil
_process: subprocess.Popen | None = None
_process_lock = threading.Lock()

SUSPEND_SURE = 30           # saniye — bu kadar heartbeat gelmezse uyku (overlay)
KAPAT_SURE   = 45           # saniye — heartbeat kesilirse desktop modunda kapat
DESKTOP_MODE = os.getenv("DESKTOP_MODE", "false").lower() in ("1", "true", "yes")


def _heartbeat_izle():
    global _suspended
    while True:
        time.sleep(10)
        with _heartbeat_lock:
            gecen = time.time() - _son_heartbeat
        _suspended = gecen > SUSPEND_SURE
        # Desktop modunda: KAPAT_SURE saniye heartbeat gelmezse kapat.
        # Sayfa yenilemede (Cmd+Shift+R) heartbeat ~2-5s içinde geri döner,
        # bu eşiğe ulaşmaz. Sekme kapatıldığında heartbeat hiç gelmez → kapanır.
        if DESKTOP_MODE and gecen > KAPAT_SURE:
            logger.info("Desktop modu: tarayıcı bağlantısı kesildi (%.0fs), uygulama kapatılıyor.", gecen)
            os.kill(os.getpid(), signal.SIGINT)


threading.Thread(target=_heartbeat_izle, daemon=True).start()


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _guvenli_yol(dizin: Path, ad: str) -> Path | None:
    yol = (dizin / ad).resolve()
    if dizin.resolve() not in yol.parents and yol != dizin.resolve():
        return None
    return yol


def _history_kaydet() -> None:
    mevcut = [d for d in HISTORY_DIR.iterdir() if d.is_dir()]
    mevcut.sort(key=lambda d: d.stat().st_mtime)
    while len(mevcut) >= HISTORY_LIMIT:
        shutil.rmtree(mevcut.pop(0))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef = HISTORY_DIR / ts
    hedef.mkdir()

    dosyalar_kopyalandi = []
    for ad in IZIN_VERILEN_CIKTILAR:
        kaynak = OUTPUT_DIR / ad
        if kaynak.exists():
            shutil.copy2(kaynak, hedef / ad)
            dosyalar_kopyalandi.append(ad)

    meta = {
        "zaman": ts,
        "dosyalar": dosyalar_kopyalandi,
    }
    (hedef / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    logger.info(f"History kaydedildi: {ts}")


def _surec_calistir(mod: str) -> None:
    global _process
    with _process_lock:
        if _process and _process.poll() is None:
            return
        cmd = [sys.executable, str(BASE_DIR / "run.py"), mod]
        _process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )

    def _bekle():
        global _process
        hata_mesaji: str | None = None
        try:
            out, _ = _process.communicate(timeout=600)
            if out:
                logger.info(f"[{mod}] çıktı:\n{out}")
            if _process.returncode != 0:
                hata_mesaji = f"Alt süreç hata kodu {_process.returncode} ile sonlandı."
                logger.error(f"[{mod}] {hata_mesaji}")
        except subprocess.TimeoutExpired:
            try:
                _process.kill()
                _process.wait(timeout=5)
            except Exception:
                pass
            hata_mesaji = "Zaman aşımı (10 dakika). Alt süreç sonlandırıldı."
            logger.error(f"[{mod}] {hata_mesaji}")
        except Exception as e:
            hata_mesaji = f"Beklenmeyen hata: {e}"
            logger.error(f"[{mod}] {hata_mesaji}", exc_info=True)

        # Eğer alt süreç workflow state'i temizleyemediyse HATA'ya çek.
        if hata_mesaji:
            try:
                from workflow import oku as _wf_oku, guncelle as _wf_guncelle, Durum as _WfDurum
                mevcut = _wf_oku().get("durum")
                if mevcut and mevcut not in (_WfDurum.IDLE, _WfDurum.HATA,
                                              _WfDurum.JIRA_TAMAMLANDI,
                                              _WfDurum.SUREC_TAMAMLANDI,
                                              _WfDurum.BRD_TAMAMLANDI,
                                              _WfDurum.ONAY_BEKLENIYOR,
                                              _WfDurum.TEKNIK_ANALIZ_ONAY_BEKLENIYOR,
                                              _WfDurum.BRD_REVIZE_BEKLENIYOR):
                    try:
                        _wf_guncelle(_WfDurum.HATA, hata_mesaji, hata=hata_mesaji)
                    except ValueError:
                        # Geçiş izinli değilse zorla sıfırla
                        from workflow import sifirla as _wf_sifirla
                        _wf_sifirla()
                        logger.warning(f"[{mod}] Workflow zorla sıfırlandı.")
            except Exception:
                logger.exception(f"[{mod}] Workflow temizleme başarısız.")

    threading.Thread(target=_bekle, daemon=True).start()


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    global _son_heartbeat, _suspended
    with _heartbeat_lock:
        _son_heartbeat = time.time()
    _suspended = False
    return jsonify({"ok": True, "desktop_mode": DESKTOP_MODE})


@app.route("/api/version", methods=["GET"])
def version_bilgi():
    try:
        commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%h|%s|%ci"], cwd=BASE_DIR, text=True
        ).strip()
        hash_, mesaj, tarih = commit.split("|", 2)
        return jsonify({"hash": hash_, "mesaj": mesaj, "tarih": tarih[:19], "hata": None})
    except Exception as e:
        return jsonify({"hash": "?", "mesaj": "Git bilgisi alınamadı", "tarih": "", "hata": str(e)})


@app.route("/api/update", methods=["POST"])
def guncelle():
    if _auth_aktif_mi() and not _giris_yapildi_mi():
        return jsonify({"error": "Yetkisiz"}), 403
    try:
        # git pull
        pull = subprocess.run(
            ["git", "pull"], cwd=BASE_DIR, capture_output=True, text=True, timeout=60
        )
        cikti = (pull.stdout + pull.stderr).strip()

        if "Already up to date" in cikti or "Zaten güncel" in cikti:
            return jsonify({"ok": True, "guncelleme_var": False, "mesaj": "Zaten en güncel sürümdesiniz."})

        # Bağımlılıklar değiştiyse güncelle
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(BASE_DIR / "requirements.txt"), "-q"],
            capture_output=True, timeout=120
        )

        logger.info("Güncelleme tamamlandı, uygulama yeniden başlatılıyor...")

        # 1 saniye sonra kendini yeniden başlat (os.execv = aynı PID, temiz restart)
        def _yeniden_basla():
            time.sleep(1)
            os.execv(sys.executable, [sys.executable] + sys.argv)

        threading.Thread(target=_yeniden_basla, daemon=True).start()

        return jsonify({"ok": True, "guncelleme_var": True, "mesaj": cikti, "yeniden_basliyor": True})

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "mesaj": "Zaman aşımı — ağ bağlantısını kontrol edin."}), 500
    except Exception as e:
        return jsonify({"ok": False, "mesaj": str(e)}), 500


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    if not DESKTOP_MODE:
        return jsonify({"ok": False}), 200
    def _kapat():
        time.sleep(2)
        logger.info("Desktop modu: sekme kapatıldı, uygulama kapatılıyor.")
        os.kill(os.getpid(), signal.SIGINT)
    threading.Thread(target=_kapat, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/workflow-state")
def workflow_state():
    import workflow as wf
    ozet = wf.ozet()
    ozet["suspended"] = _suspended
    return jsonify(ozet)


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Dosya seçilmedi"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Dosya adı boş"}), 400

    suffix = Path(f.filename).suffix.lower()
    if suffix not in IZIN_VERILEN_UZANTILAR:
        return jsonify({"error": f"Desteklenmeyen dosya türü: {suffix}"}), 400

    # Mevcut input'u temizle
    for eski in INPUT_DIR.iterdir():
        if eski.is_file():
            eski.unlink()

    guvenli_ad = Path(f.filename).name
    hedef = INPUT_DIR / guvenli_ad
    f.save(str(hedef))
    logger.info(f"Dosya yüklendi: {guvenli_ad}")
    return jsonify({"ok": True, "dosya": guvenli_ad})


@app.route("/api/run", methods=["POST"])
def run():
    import workflow as wf
    data = request.get_json(silent=True) or {}
    pipeline = data.get("pipeline", "")

    if pipeline not in ("surec", "brd"):
        return jsonify({"error": "Geçersiz pipeline. 'surec' veya 'brd' olmalı."}), 400

    ozet = wf.ozet()
    if ozet["calisiyor"]:
        return jsonify({"error": "Bir işlem zaten çalışıyor."}), 409

    # input kontrol
    dosyalar = [f for f in INPUT_DIR.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not dosyalar:
        return jsonify({"error": "Önce bir doküman yükleyin."}), 400

    try:
        wf.baslat(pipeline)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    mod = "surec_analizi" if pipeline == "surec" else "brd_analizi"
    _surec_calistir(mod)
    logger.info(f"Pipeline başlatıldı: {pipeline}")
    return jsonify({"ok": True, "pipeline": pipeline})


@app.route("/api/run-teknik", methods=["POST"])
def run_teknik():
    import workflow as wf
    ozet = wf.ozet()
    if ozet["calisiyor"]:
        return jsonify({"error": "Bir işlem zaten çalışıyor."}), 409

    surec_cikti = OUTPUT_DIR / "surec-analizi.md"

    # INPUT_DIR'de .md veya .txt varsa → surec-analizi.md olarak kullan
    input_dosyalar = [f for f in INPUT_DIR.iterdir() if f.is_file() and not f.name.startswith(".")]
    md_dosya = next((f for f in input_dosyalar if f.suffix.lower() in (".md", ".txt")), None)
    if md_dosya:
        shutil.copy2(md_dosya, surec_cikti)
        logger.info(f"Yüklenen dosya surec-analizi.md olarak kopyalandı: {md_dosya.name}")
    elif not surec_cikti.exists():
        return jsonify({"error": "Süreç analizi bulunamadı. Bir süreç analizi dokümanı (.md / .txt) yükleyin ya da önce tam pipeline çalıştırın."}), 400

    try:
        wf.baslat_teknik()
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    _surec_calistir("teknik_analiz")
    logger.info("Sadece teknik analiz başlatıldı.")
    return jsonify({"ok": True})


@app.route("/api/approve", methods=["POST"])
def approve():
    import workflow as wf
    try:
        state = wf.onayla()
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    _surec_calistir("teknik_analiz")
    logger.info("Analist onayı verildi.")
    return jsonify({"ok": True, "durum": state["durum"]})


@app.route("/api/reject", methods=["POST"])
def reject():
    import workflow as wf
    try:
        state = wf.reddet()
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    logger.info("Analist reddi.")
    return jsonify({"ok": True, "durum": state["durum"]})


@app.route("/api/upload-revised-brd", methods=["POST"])
def upload_revised_brd():
    import workflow as wf

    ozet = wf.ozet()
    if not ozet["brd_revize_bekleniyor"]:
        return jsonify({"error": "BRD revizyonu beklenmiyordu."}), 409

    if "file" not in request.files:
        return jsonify({"error": "Dosya seçilmedi"}), 400

    f = request.files["file"]
    suffix = Path(f.filename).suffix.lower()
    if suffix not in IZIN_VERILEN_UZANTILAR:
        return jsonify({"error": f"Desteklenmeyen dosya türü: {suffix}"}), 400

    # input/ klasörünü güncelle
    for eski in INPUT_DIR.iterdir():
        if eski.is_file():
            eski.unlink()
    hedef = INPUT_DIR / Path(f.filename).name
    f.save(str(hedef))

    try:
        state = wf.brd_revize_tamamlandi()
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    _surec_calistir("kapsam_analizi")
    logger.info("Revize BRD yüklendi, kapsam analizi başlatıldı.")
    return jsonify({"ok": True, "durum": state["durum"]})


@app.route("/api/skip-kapsam", methods=["POST"])
def skip_kapsam():
    """Kapsam analizini atla — BRD_REVIZE_BEKLENIYOR → IDLE (sadece final kaydet)."""
    import workflow as wf
    from agent import brd_final_kaydet

    ozet = wf.ozet()
    if not ozet["brd_revize_bekleniyor"]:
        return jsonify({"error": "BRD revizyonu beklenmiyordu."}), 409

    dosyalar = [f for f in INPUT_DIR.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not dosyalar:
        return jsonify({"error": "Kaydedilecek dosya yok."}), 400

    try:
        brd_final_kaydet()
        wf.guncelle(wf.Durum.BRD_TAMAMLANDI, "Kapsam analizi atlandı, BRD kaydedildi.")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    _history_kaydet()
    return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
@admin_gerekli
def reset():
    import workflow as wf
    wf.sifirla()
    logger.info("Workflow sıfırlandı.")
    return jsonify({"ok": True})


@app.route("/api/output/<dosya_adi>")
def output_dosyasi(dosya_adi: str):
    yol = _guvenli_yol(OUTPUT_DIR, dosya_adi)
    if not yol or dosya_adi not in IZIN_VERILEN_CIKTILAR:
        abort(404)
    if not yol.exists():
        return jsonify({"error": "Dosya henüz oluşturulmadı"}), 404
    icerik = yol.read_text(encoding="utf-8")
    if dosya_adi.endswith(".html"):
        return icerik, 200, {"Content-Type": "text/html; charset=utf-8"}
    return icerik, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/output/delete", methods=["POST"])
def output_sil():
    data = request.get_json(force=True) or {}
    dosya_adi = (data.get("dosya") or "").strip()
    if not dosya_adi or dosya_adi not in IZIN_VERILEN_CIKTILAR:
        return jsonify({"ok": False, "error": "Geçersiz dosya"}), 400
    yol = _guvenli_yol(OUTPUT_DIR, dosya_adi)
    if not yol or not yol.exists():
        return jsonify({"ok": False, "error": "Dosya bulunamadı"}), 404
    yol.unlink()
    logger.info(f"Çıktı silindi: {dosya_adi}")
    return jsonify({"ok": True})


@app.route("/api/outputs")
def outputs():
    sonuc = {}
    for ad in IZIN_VERILEN_CIKTILAR:
        yol = OUTPUT_DIR / ad
        sonuc[ad] = {
            "var": yol.exists(),
            "boyut": yol.stat().st_size if yol.exists() else 0,
            "guncelleme": yol.stat().st_mtime if yol.exists() else None,
        }
    return jsonify(sonuc)


@app.route("/api/history")
def history():
    girdi = []
    for d in sorted(HISTORY_DIR.iterdir(), reverse=True):
        meta_yol = d / "meta.json"
        if meta_yol.exists():
            try:
                meta = json.loads(meta_yol.read_text())
                girdi.append({"id": d.name, **meta})
            except Exception:
                pass
    return jsonify(girdi[:HISTORY_LIMIT])


@app.route("/api/history/<arsiv_id>/<dosya_adi>")
def history_dosyasi(arsiv_id: str, dosya_adi: str):
    if ".." in arsiv_id or "/" in arsiv_id:
        abort(400)
    if dosya_adi not in IZIN_VERILEN_CIKTILAR:
        abort(404)
    yol = HISTORY_DIR / arsiv_id / dosya_adi
    if not yol.exists():
        abort(404)
    return yol.read_text(encoding="utf-8"), 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/save-history", methods=["POST"])
def save_history():
    _history_kaydet()
    return jsonify({"ok": True})


def _zip_guvenlimi(member_path: str) -> bool:
    """Zip üyesinin güvenli olup olmadığını kontrol et (zip-slip + atlanacak klasörler)."""
    p = Path(member_path)
    # Path traversal
    if ".." in p.parts:
        return False
    # Atlanacak klasör
    for parca in p.parts:
        if parca in ZIP_ATLA_KLASORLER:
            return False
    return True


def _zip_cikart(zip_yolu: str, hedef_dizin: Path, temizle: bool = True) -> dict:
    """
    Zip dosyasını hedef_dizin içine çıkart.
    Güvenlik kontrolleri: zip-slip, atlanacak klasörler, boyut limiti, uzantı filtresi.
    Returns: {"yuklenenler": [...], "atlananlar": int, "toplam_boyut": int}
    """
    if temizle:
        shutil.rmtree(hedef_dizin, ignore_errors=True)
    hedef_dizin.mkdir(parents=True, exist_ok=True)

    yuklenenler = []
    atlanan = 0
    toplam_boyut = 0

    with zipfile.ZipFile(zip_yolu, "r") as zf:
        for uye in zf.infolist():
            if uye.is_dir():
                continue

            # Güvenlik + klasör filtresi
            if not _zip_guvenlimi(uye.filename):
                atlanan += 1
                continue

            p = Path(uye.filename)
            if p.suffix.lower() not in UI_UZANTILAR:
                atlanan += 1
                continue

            # Boyut kontrolleri
            if uye.file_size > ZIP_MAX_DOSYA_BOYUTU:
                atlanan += 1
                continue
            if toplam_boyut + uye.file_size > ZIP_MAX_TOPLAM_BOYUT:
                atlanan += 1
                continue
            # Zip bomb koruması: sıkıştırma oranı > 100 ise reddet
            if uye.compress_size > 0 and uye.file_size / uye.compress_size > 100:
                logger.warning(f"Zip bomb adayı atlandı: {uye.filename} (oran: {uye.file_size // max(uye.compress_size,1)}x)")
                atlanan += 1
                continue

            # Hedef yolu hesapla — zip içindeki ilk ortak ön eki kır
            hedef_yol = (hedef_dizin / uye.filename).resolve()
            if not str(hedef_yol).startswith(str(hedef_dizin.resolve())):
                atlanan += 1
                continue

            hedef_yol.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(uye) as src:
                hedef_yol.write_bytes(src.read())

            yuklenenler.append(str(p))
            toplam_boyut += uye.file_size

    return {"yuklenenler": yuklenenler, "atlananlar": atlanan, "toplam_boyut": toplam_boyut}


@app.route("/api/upload-ui-project", methods=["POST"])
def upload_ui_project():
    """
    Proje export zip dosyasını yükle, çıkart ve reference/ui-code/ içine kaydet.
    mode: 'replace' (varsayılan) — mevcut dosyaları temizler, 'merge' — üzerine ekler.
    """
    if "file" not in request.files:
        return jsonify({"error": "Dosya seçilmedi"}), 400

    f = request.files["file"]
    if not f.filename or Path(f.filename).suffix.lower() != ".zip":
        return jsonify({"error": "Yalnızca .zip dosyası kabul edilir"}), 400

    mode = request.form.get("mode", "replace")

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        f.save(tmp.name)
        tmp_yol = tmp.name

    try:
        sonuc = _zip_cikart(tmp_yol, UI_CODE_DIR, temizle=(mode == "replace"))
    except zipfile.BadZipFile:
        return jsonify({"error": "Geçersiz zip dosyası"}), 400
    except Exception as e:
        logger.error(f"Zip çıkartma hatası: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(tmp_yol)
        except Exception:
            pass

    logger.info(f"UI proje yüklendi: {len(sonuc['yuklenenler'])} dosya, {sonuc['atlananlar']} atlandı")
    return jsonify({
        "ok": True,
        "dosya_sayisi": len(sonuc["yuklenenler"]),
        "atlananlar": sonuc["atlananlar"],
        "toplam_boyut": sonuc["toplam_boyut"],
    })


@app.route("/api/upload-ui-code", methods=["POST"])
def upload_ui_code():
    """Tekil UI kaynak dosyalarını yükle (webkitdirectory veya çoklu seçim)."""
    dosyalar = request.files.getlist("files")
    if not dosyalar:
        return jsonify({"error": "Dosya seçilmedi"}), 400

    yuklenenler = []
    hatalar = []

    for f in dosyalar:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix.lower()
        if suffix not in UI_UZANTILAR:
            hatalar.append(f"{f.filename}: desteklenmeyen tür")
            continue

        # webkitdirectory ile gelen göreceli yolu koru
        goreceli = f.filename.replace("\\", "/").lstrip("/")
        if ".." in goreceli:
            continue
        hedef = UI_CODE_DIR / goreceli
        # Path traversal koruması
        if not str(hedef.resolve()).startswith(str(UI_CODE_DIR.resolve())):
            continue
        hedef.parent.mkdir(parents=True, exist_ok=True)
        f.save(str(hedef))
        yuklenenler.append(goreceli)

    logger.info(f"UI kodu yüklendi: {len(yuklenenler)} dosya")
    return jsonify({"ok": True, "yuklenenler": yuklenenler, "hatalar": hatalar})


@app.route("/api/ui-files")
def ui_files():
    """Yüklü UI dosyalarını listele."""
    from agent import ui_dosyalari_listele
    return jsonify(ui_dosyalari_listele())


@app.route("/api/ui-files/content", methods=["GET"])
def ui_file_icerik():
    """Göreceli yol ile UI dosyası içeriğini döndür. ?yol=src/components/Button.tsx"""
    goreceli = request.args.get("yol", "")
    if not goreceli or ".." in goreceli:
        abort(400)
    yol = (UI_CODE_DIR / goreceli).resolve()
    if not str(yol).startswith(str(UI_CODE_DIR.resolve())):
        abort(400)
    if not yol.exists() or yol.suffix.lower() not in UI_UZANTILAR:
        abort(404)
    return yol.read_text(encoding="utf-8", errors="replace"), 200, {
        "Content-Type": "text/plain; charset=utf-8"
    }


@app.route("/api/ui-files/delete", methods=["POST"])
def ui_file_sil():
    data = request.get_json(silent=True) or {}
    goreceli = data.get("yol", "")
    if not goreceli or ".." in goreceli:
        abort(400)
    yol = (UI_CODE_DIR / goreceli).resolve()
    if not str(yol).startswith(str(UI_CODE_DIR.resolve())):
        abort(400)
    if yol.exists():
        yol.unlink()
        # Boş klasörleri temizle
        try:
            yol.parent.rmdir()
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/ui-files/clear", methods=["POST"])
def ui_files_temizle():
    """Tüm UI dosyalarını sil."""
    shutil.rmtree(UI_CODE_DIR, ignore_errors=True)
    UI_CODE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("UI kodu temizlendi.")
    return jsonify({"ok": True})


@app.route("/api/save-output", methods=["POST"])
def save_output():
    """Kullanıcının UI'da düzenlediği çıktıyı kaydet."""
    data = request.get_json(silent=True) or {}
    dosya_adi = data.get("dosya", "")
    icerik = data.get("icerik", "")

    if dosya_adi not in IZIN_VERILEN_CIKTILAR:
        return jsonify({"error": "Geçersiz dosya adı"}), 400
    if len(icerik) > 500 * 1024:
        return jsonify({"error": "İçerik çok büyük (max 500 KB)"}), 413

    yol = OUTPUT_DIR / dosya_adi
    yol.write_text(icerik, encoding="utf-8")
    logger.info(f"Çıktı düzenlendi: {dosya_adi}")
    return jsonify({"ok": True})


@app.route("/api/rerun", methods=["POST"])
def rerun():
    """
    Mevcut çıktıyı düzeltme notu ile yeniden üret.
    Body: { "dosya": "surec-analizi.md", "duzeltme": "..." }
    Workflow state değiştirmez — bağımsız çalışır.
    """
    data = request.get_json(silent=True) or {}
    dosya_adi = data.get("dosya", "")
    duzeltme = data.get("duzeltme", "").strip()

    if dosya_adi not in IZIN_VERILEN_CIKTILAR:
        return jsonify({"error": "Geçersiz dosya adı"}), 400
    if not duzeltme:
        return jsonify({"error": "Düzeltme notu boş"}), 400

    if not _rerun_lock.acquire(blocking=False):
        return jsonify({"error": "Başka bir revize işlemi devam ediyor"}), 409

    # Düzeltme notunu geçici dosyaya yaz
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(duzeltme)
        tmp_yol = tmp.name

    def _calistir():
        try:
            cmd = [sys.executable, str(BASE_DIR / "run.py"), "yeniden_calistir", dosya_adi, tmp_yol]
            proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                logger.error(f"rerun hatası: {proc.stderr}")
            else:
                logger.info(f"rerun tamamlandı: {dosya_adi}")
        except Exception as e:
            logger.error(f"rerun exception: {e}")
        finally:
            try:
                os.unlink(tmp_yol)
            except Exception:
                pass
            _rerun_lock.release()

    threading.Thread(target=_calistir, daemon=True).start()
    logger.info(f"Yeniden çalıştırma başlatıldı: {dosya_adi}")
    return jsonify({"ok": True, "dosya": dosya_adi})


@app.route("/api/rerun-status/<dosya_adi>")
def rerun_status(dosya_adi: str):
    """Yeniden çalıştırılan dosyanın son güncelleme zamanını döndür."""
    if dosya_adi not in IZIN_VERILEN_CIKTILAR:
        abort(400)
    yol = OUTPUT_DIR / dosya_adi
    if not yol.exists():
        return jsonify({"var": False})
    return jsonify({"var": True, "guncelleme": yol.stat().st_mtime})




def _env_yaz(degiskenler: dict) -> None:
    """Mevcut .env'i koru, sadece belirtilen anahtarları güncelle/ekle. Atomik yazım + 0o600."""
    env_yol = BASE_DIR / ".env"
    satirlar = []
    guncellenenler = set()

    if env_yol.exists():
        for satir in env_yol.read_text(encoding="utf-8").splitlines():
            e = satir.strip()
            if e and not e.startswith("#") and "=" in e:
                k = e.split("=", 1)[0].strip()
                if k in degiskenler:
                    satirlar.append(f"{k}={degiskenler[k]}")
                    guncellenenler.add(k)
                    continue
            satirlar.append(satir)

    for k, v in degiskenler.items():
        if k not in guncellenenler:
            satirlar.append(f"{k}={v}")

    tmp = env_yol.with_suffix(".env.tmp")
    tmp.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(env_yol)


def _maskele(deger: str) -> str:
    if not deger or len(deger) < 8:
        return "***"
    return deger[:6] + "..." + deger[-4:]


def _claude_cli_var_mi() -> bool:
    return bool(shutil.which("claude"))


# ─── Auth Route'ları ──────────────────────────────────────────────────────────

@app.route("/login")
def login_sayfasi():
    if _giris_yapildi_mi():
        return redirect("/")
    return render_template("login.html")


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    ip = request.remote_addr or "unknown"
    if _brute_force_kontrol(ip):
        return jsonify({"error": "Çok fazla başarısız giriş denemesi. Lütfen bekleyin."}), 429

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Kullanıcı adı ve şifre gerekli"}), 400
    users = _kullanicilari_oku()
    if not users:
        return jsonify({"error": "Henüz kullanıcı tanımlanmamış. manage_users.py ile ilk kullanıcıyı oluşturun."}), 403
    hashed = users.get(username)
    if not hashed or not check_password_hash(hashed, password):
        _basarisiz_giris_kaydet(ip)
        return jsonify({"error": "Kullanıcı adı veya şifre hatalı"}), 401
    session["username"] = username
    session.permanent = True
    logger.info(f"Giriş: {username}")
    return jsonify({"ok": True, "username": username})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    username = session.pop("username", None)
    if username:
        logger.info(f"Çıkış: {username}")
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    return jsonify({"username": session.get("username"), "is_admin": _admin_mi()})


# ─── Kullanıcı Yönetimi ───────────────────────────────────────────────────────

@app.route("/api/users", methods=["GET"])
def kullanici_listele():
    if not _admin_mi():
        return jsonify({"error": "Yetkisiz"}), 403
    users = _kullanicilari_oku()
    return jsonify({"users": list(users.keys())})


@app.route("/api/users", methods=["POST"])
def kullanici_ekle():
    if not _admin_mi():
        return jsonify({"error": "Yetkisiz"}), 403
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Kullanıcı adı ve şifre gerekli"}), 400
    if len(username) < 2 or not username.replace("_", "").replace("-", "").replace(".", "").isalnum():
        return jsonify({"error": "Kullanıcı adı yalnızca harf, rakam, -, _ ve . içerebilir (min 2 karakter)"}), 400
    if len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalı"}), 400
    users = _kullanicilari_oku()
    if username in users:
        return jsonify({"error": f"'{username}' zaten mevcut"}), 409
    users[username] = generate_password_hash(password)
    _kullanicilari_yaz(users)
    logger.info(f"Kullanıcı eklendi: {username}")
    return jsonify({"ok": True, "username": username})


@app.route("/api/users/<username>", methods=["DELETE"])
def kullanici_sil(username):
    if not _admin_mi():
        return jsonify({"error": "Yetkisiz"}), 403
    username = username.lower()
    if username == session.get("username"):
        return jsonify({"error": "Kendi hesabınızı silemezsiniz"}), 400
    users = _kullanicilari_oku()
    if username not in users:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 404
    del users[username]
    _kullanicilari_yaz(users)
    logger.info(f"Kullanıcı silindi: {username}")
    return jsonify({"ok": True})


@app.route("/api/users/<username>/password", methods=["POST"])
def kullanici_sifre_degistir(username):
    if not _admin_mi():
        return jsonify({"error": "Yetkisiz"}), 403
    username = username.lower()
    data = request.get_json(silent=True) or {}
    yeni_sifre = data.get("password", "")
    if len(yeni_sifre) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalı"}), 400
    users = _kullanicilari_oku()
    if username not in users:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 404
    users[username] = generate_password_hash(yeni_sifre)
    _kullanicilari_yaz(users)
    logger.info(f"Şifre değiştirildi: {username}")
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["GET"])
def settings_oku():
    env = _env_oku()
    api_key = env.get("ANTHROPIC_API_KEY", "")
    cli_mod = env.get("USE_CLAUDE_CLI", "false").lower() in ("1", "true", "yes")
    thinking = env.get("EXTENDED_THINKING", "false").lower() in ("1", "true", "yes")
    return jsonify({
        "api_key_set": bool(api_key),
        "api_key_masked": _maskele(api_key) if api_key else "",
        "cli_mod": cli_mod,
        "claude_cli_var": _claude_cli_var_mi(),
        "extended_thinking": thinking,
    })


@app.route("/api/settings", methods=["POST"])
def settings_kaydet():
    data = request.get_json(silent=True) or {}
    degisiklikler = {}

    api_key = data.get("api_key", "").strip()
    if api_key:
        if not api_key.startswith("sk-"):
            return jsonify({"error": "Geçersiz API key formatı (sk- ile başlamalı)"}), 400
        degisiklikler["ANTHROPIC_API_KEY"] = api_key
        os.environ["ANTHROPIC_API_KEY"] = api_key

    if "cli_mod" in data:
        deger = "true" if data["cli_mod"] else "false"
        degisiklikler["USE_CLAUDE_CLI"] = deger
        os.environ["USE_CLAUDE_CLI"] = deger

    if "extended_thinking" in data:
        deger = "true" if data["extended_thinking"] else "false"
        degisiklikler["EXTENDED_THINKING"] = deger
        os.environ["EXTENDED_THINKING"] = deger

    if not degisiklikler:
        return jsonify({"error": "Değiştirilecek ayar yok"}), 400

    _env_yaz(degisiklikler)
    logger.info(f"Ayarlar güncellendi: {list(degisiklikler.keys())}")

    env = _env_oku()
    api_key_guncel = env.get("ANTHROPIC_API_KEY", "")
    return jsonify({
        "ok": True,
        "masked": _maskele(api_key_guncel) if api_key_guncel else "",
        "cli_mod": env.get("USE_CLAUDE_CLI", "false").lower() in ("1", "true", "yes"),
        "extended_thinking": env.get("EXTENDED_THINKING", "false").lower() in ("1", "true", "yes"),
    })


# ─── Çıktı Kalite Skoru ───────────────────────────────────────────────────────

@app.route("/api/cikti/<dosya>/skor", methods=["GET"])
def cikti_skor_getir(dosya):
    """Bir çıktı dosyasının kalite skorunu döndürür (0-100, sorun listesi ile)."""
    from skills.kalite import cikti_skoru
    if dosya not in IZIN_VERILEN_CIKTILAR:
        return jsonify({"ok": False, "error": "Geçersiz dosya"}), 400
    return jsonify(cikti_skoru(dosya))


@app.route("/api/cikti/<dosya>/skor/duzelt", methods=["POST"])
def cikti_skor_duzelt(dosya):
    """Skor sorunlarını otomatik düzeltmek için Yeniden Çalıştır + AI."""
    import workflow as wf
    from skills.kalite import cikti_skoru, duzeltme_notu_uret
    from skills.base import yeniden_calistir

    if dosya not in IZIN_VERILEN_CIKTILAR:
        return jsonify({"ok": False, "error": "Geçersiz dosya"}), 400
    if wf.ozet()["calisiyor"]:
        return jsonify({"ok": False, "error": "Bir analiz çalışıyor, bitince tekrar deneyin"}), 409

    onceki = cikti_skoru(dosya)
    if not onceki.get("ok"):
        return jsonify(onceki), 404
    if not onceki.get("sorunlar"):
        return jsonify({"ok": True, "mesaj": "Sorun yok, düzeltmeye gerek yok.", "skor": onceki["skor"]})

    notu = duzeltme_notu_uret(onceki)
    try:
        yeniden_calistir(dosya, notu)
    except Exception as e:
        logger.error("Skor düzeltme hatası: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

    sonra = cikti_skoru(dosya)
    return jsonify({
        "ok": True,
        "onceki_skor": onceki["skor"],
        "yeni_skor": sonra.get("skor"),
        "uygulanan_not": notu,
        "yeni_sonuclar": sonra,
    })


# ─── Soru Defteri ─────────────────────────────────────────────────────────────

@app.route("/api/sorular", methods=["GET"])
def sorular_getir():
    """Soru defterini döndürür. ?parse=true ile çıktıları yeniden tarar."""
    from skills.sorular import sorular_yukle, parse_ve_birlestir
    if request.args.get("parse") in ("1", "true", "yes"):
        try:
            data = parse_ve_birlestir()
        except Exception as e:
            logger.error("Soru parse hatası: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500
    else:
        data = sorular_yukle()
    return jsonify({"ok": True, **data})


@app.route("/api/sorular/parse", methods=["POST"])
def sorular_parse():
    """Çıktıları yeniden tarar ve soru defterini günceller."""
    from skills.sorular import parse_ve_birlestir
    try:
        data = parse_ve_birlestir()
        return jsonify({"ok": True, **data})
    except Exception as e:
        logger.error("Soru parse hatası: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/sorular/<soru_id>", methods=["POST"])
def soru_guncelle_endpoint(soru_id):
    """Bir sorunun durumunu/cevabını günceller.

    Body: {kaynak_dosya, durum, cevap?, varsayim?}
    """
    from skills.sorular import soru_guncelle
    payload = request.get_json(silent=True) or {}
    kaynak = (payload.get("kaynak_dosya") or "").strip()
    durum = (payload.get("durum") or "").strip()
    cevap = payload.get("cevap")
    varsayim = payload.get("varsayim")

    if not kaynak or not durum:
        return jsonify({"ok": False, "error": "kaynak_dosya ve durum zorunlu"}), 400
    try:
        sonuc = soru_guncelle(soru_id, kaynak, durum, cevap=cevap, varsayim=varsayim)
        logger.info("Soru güncellendi: %s/%s → %s", kaynak, soru_id, durum)
        return jsonify({"ok": True, "soru": sonuc})
    except ValueError as e:
        msg = str(e)
        # "Geçersiz durum" → 400, "Soru bulunamadı" → 404
        http = 400 if msg.startswith("Geçersiz") else 404
        return jsonify({"ok": False, "error": msg}), http
    except Exception as e:
        logger.error("Soru güncelleme hatası: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/sorular/<soru_id>", methods=["DELETE"])
def soru_sil_endpoint(soru_id):
    """Bir soruyu defterden tamamen kaldırır.
    Query: ?kaynak_dosya=teknik-analiz.md
    """
    from skills.sorular import soru_sil
    kaynak = (request.args.get("kaynak_dosya") or "").strip()
    if not kaynak:
        return jsonify({"ok": False, "error": "kaynak_dosya query parametresi zorunlu"}), 400
    silindi = soru_sil(soru_id, kaynak)
    if not silindi:
        return jsonify({"ok": False, "error": "Soru bulunamadı"}), 404
    return jsonify({"ok": True})


@app.route("/api/sorular/uygula", methods=["POST"])
def sorular_uygula():
    """Cevaplanmış/varsayım sorularını refine ile ilgili analize işler.

    Body: {"zorla": false}  → True ise zaten uygulanmış olanları da tekrar uygular.
    Her kaynak_dosya için ayrı refine çağrısı yapılır (atomik değil — birinde hata
    olursa diğerleri devam eder; sonuç listesi durumu gösterir).
    """
    import workflow as wf
    from skills.sorular import (
        uygulanacak_sorular, duzeltme_notu_olustur, uygulandi_isaretle,
        parse_ve_birlestir,
    )
    from skills.base import yeniden_calistir

    if wf.ozet()["calisiyor"]:
        return jsonify({"ok": False, "error": "Başka bir analiz çalışıyor. Bitince tekrar deneyin."}), 409

    payload = request.get_json(silent=True) or {}
    zorla = bool(payload.get("zorla", False))

    gruplar = uygulanacak_sorular(zorla=zorla)
    if not gruplar:
        return jsonify({
            "ok": True,
            "mesaj": "Uygulanacak yeni cevap/varsayım yok.",
            "sonuclar": [],
        })

    sonuclar = []
    for kaynak, sorular in gruplar.items():
        # Sadece bilinen analiz dosyalarına refine uygula
        if kaynak not in IZIN_VERILEN_CIKTILAR:
            sonuclar.append({"kaynak_dosya": kaynak, "ok": False, "error": "Bilinmeyen dosya, atlandı"})
            continue
        if not (OUTPUT_DIR / kaynak).exists():
            sonuclar.append({"kaynak_dosya": kaynak, "ok": False, "error": "Dosya bulunamadı"})
            continue
        try:
            not_metni = duzeltme_notu_olustur(sorular)
            yeniden_calistir(kaynak, not_metni)
            for s in sorular:
                uygulandi_isaretle(s["id"], kaynak)
            sonuclar.append({
                "kaynak_dosya": kaynak,
                "ok": True,
                "uygulanan_sayi": len(sorular),
                "uygulanan_ids": [s["id"] for s in sorular],
            })
            logger.info("Sorular uygulandı: %s — %d soru", kaynak, len(sorular))
        except Exception as e:
            logger.error("Refine hatası (%s): %s", kaynak, e)
            sonuclar.append({"kaynak_dosya": kaynak, "ok": False, "error": str(e)})

    # Soruları yeniden tara — AI çıktıyı değiştirdi, parser güncel veriyi alsın
    try:
        parse_ve_birlestir()
    except Exception:
        pass

    basari_sayisi = sum(1 for s in sonuclar if s["ok"])
    return jsonify({
        "ok": basari_sayisi > 0,
        "mesaj": f"{basari_sayisi}/{len(sonuclar)} dosya güncellendi",
        "sonuclar": sonuclar,
    })


@app.route("/api/sorular/paylasim", methods=["GET"])
def sorular_paylasim():
    """Bekleyen/açık soruları kopyala-yapıştır için düz metin döndürür."""
    from skills.sorular import paylasim_metni
    durum_param = request.args.get("durumlar", "acik,bekleniyor")
    durumlar = tuple(d.strip() for d in durum_param.split(",") if d.strip())
    metin = paylasim_metni(durumlar=durumlar)
    return jsonify({"ok": True, "metin": metin})


# ─── Prompt Yönetimi ──────────────────────────────────────────────────────────

@app.route("/api/prompts", methods=["GET"])
def prompts_listele():
    from skills.base import VARSAYILAN_PROMPTLAR, PROMPTS_PATH
    import json as _json
    try:
        ozel = _json.loads(PROMPTS_PATH.read_text(encoding="utf-8")) if PROMPTS_PATH.exists() else {}
    except Exception:
        ozel = {}
    sonuc = {}
    for kid, meta in VARSAYILAN_PROMPTLAR.items():
        sonuc[kid] = {
            "ad": meta["ad"],
            "aciklama": meta["aciklama"],
            "varsayilan": meta["icerik"],
            "ozel": ozel.get(kid),
            "icerik": ozel.get(kid, meta["icerik"]),
            "degistirildi": kid in ozel,
        }
    return jsonify(sonuc)


@app.route("/api/prompts/<skill_id>", methods=["POST"])
@admin_gerekli
def prompt_guncelle(skill_id):
    from skills.base import VARSAYILAN_PROMPTLAR, prompt_kaydet
    if skill_id not in VARSAYILAN_PROMPTLAR:
        return jsonify({"error": f"Bilinmeyen skill: {skill_id}"}), 404
    data = request.get_json(silent=True) or {}
    icerik = data.get("icerik", "").strip()
    if not icerik:
        return jsonify({"error": "İçerik boş olamaz"}), 400
    prompt_kaydet(skill_id, icerik)
    logger.info(f"Prompt güncellendi: {skill_id}")
    return jsonify({"ok": True})


@app.route("/api/prompts/<skill_id>/reset", methods=["POST"])
@admin_gerekli
def prompt_sifirla_route(skill_id):
    from skills.base import VARSAYILAN_PROMPTLAR, prompt_sifirla
    if skill_id not in VARSAYILAN_PROMPTLAR:
        return jsonify({"error": f"Bilinmeyen skill: {skill_id}"}), 404
    prompt_sifirla(skill_id)
    logger.info(f"Prompt sıfırlandı: {skill_id}")
    return jsonify({"ok": True})


# ─── Teknik Analiz Onay / Red ─────────────────────────────────────────────────

@app.route("/api/approve-teknik", methods=["POST"])
def approve_teknik():
    import workflow as wf
    try:
        state = wf.teknik_onayla()
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    _surec_calistir("jira_gonder")
    logger.info("Teknik analiz onaylandı — Jira task oluşturuluyor.")
    return jsonify({"ok": True, "durum": state["durum"]})


@app.route("/api/approve-teknik-no-jira", methods=["POST"])
def approve_teknik_no_jira():
    import workflow as wf
    try:
        state = wf.teknik_bitir()
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    logger.info("Teknik analiz onaylandı — Jira atlandı.")
    return jsonify({"ok": True, "durum": state["durum"]})


@app.route("/api/reject-teknik", methods=["POST"])
def reject_teknik():
    import workflow as wf
    try:
        state = wf.teknik_reddet()
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    logger.info("Teknik analiz reddedildi.")
    return jsonify({"ok": True, "durum": state["durum"]})


# ─── Referans Dokümanlar ──────────────────────────────────────────────────────

@app.route("/api/reference/list")
def reference_list():
    """Tüm referans kategorilerindeki dosyaları döndür."""
    sonuc = {}
    for kategori, dizin in REFERANS_DIZINLER.items():
        dosyalar = []
        if dizin and dizin.exists():
            for f in sorted(dizin.rglob("*")):
                if f.is_file() and not f.name.startswith("_") and not f.name.startswith("."):
                    try:
                        rel = str(f.relative_to(dizin))
                    except ValueError:
                        rel = f.name
                    dosyalar.append({
                        "ad": f.name,
                        "yol": rel,
                        "boyut": f.stat().st_size,
                        "uzanti": f.suffix.lower(),
                    })
        sonuc[kategori] = dosyalar
    return jsonify(sonuc)


@app.route("/api/reference/upload/<kategori>", methods=["POST"])
def reference_upload(kategori: str):
    """Referans kategorisine dosya yükle."""
    if kategori not in REFERANS_KATEGORILER:
        return jsonify({"error": f"Geçersiz kategori: {kategori}"}), 400

    dosyalar = request.files.getlist("files")
    if not dosyalar:
        f = request.files.get("file")
        if f:
            dosyalar = [f]
    if not dosyalar:
        return jsonify({"error": "Dosya seçilmedi"}), 400

    izin_uzantilar = REFERANS_KATEGORILER[kategori]
    dizin = REFERANS_DIZINLER[kategori]
    yuklenenler = []
    hatalar = []

    for f in dosyalar:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix.lower()
        if suffix not in izin_uzantilar:
            hatalar.append(f"{f.filename}: desteklenmeyen tür ({suffix})")
            continue
        guvenli_ad = Path(f.filename).name
        if ".." in guvenli_ad:
            continue
        hedef = dizin / guvenli_ad
        f.save(str(hedef))
        yuklenenler.append(guvenli_ad)
        logger.info(f"Referans yüklendi [{kategori}]: {guvenli_ad}")

    return jsonify({"ok": True, "yuklenenler": yuklenenler, "hatalar": hatalar})


@app.route("/api/reference/delete", methods=["POST"])
def reference_delete():
    """Referans dosyasını sil."""
    data = request.get_json(silent=True) or {}
    kategori = data.get("kategori", "")
    yol = data.get("yol", "")

    if kategori not in REFERANS_DIZINLER:
        return jsonify({"error": "Geçersiz kategori"}), 400
    if not yol or ".." in yol:
        abort(400)

    dizin = REFERANS_DIZINLER[kategori]
    hedef = (dizin / yol).resolve()
    if not str(hedef).startswith(str(dizin.resolve())):
        abort(400)
    if hedef.exists():
        hedef.unlink()
        logger.info(f"Referans silindi [{kategori}]: {yol}")
    return jsonify({"ok": True})


@app.route("/api/reference/content")
def reference_content():
    """Referans dosyası içeriğini döndür. ?kategori=confluence&yol=..."""
    kategori = request.args.get("kategori", "")
    yol = request.args.get("yol", "")
    if kategori not in REFERANS_DIZINLER or not yol or ".." in yol:
        abort(400)
    dizin = REFERANS_DIZINLER[kategori]
    hedef = (dizin / yol).resolve()
    if not str(hedef).startswith(str(dizin.resolve())):
        abort(400)
    if not hedef.exists():
        abort(404)
    return hedef.read_text(encoding="utf-8", errors="replace"), 200, {
        "Content-Type": "text/plain; charset=utf-8"
    }


# ─── Veri Kaynakları (Sources) ────────────────────────────────────────────────

@app.route("/api/sources")
def sources_listele():
    return jsonify({"ok": True, "sources": _load_sources()})


@app.route("/api/sources/confluence", methods=["POST"])
def sources_confluence_ekle():
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    name = (data.get("name") or "").strip() or key
    if not key:
        return jsonify({"ok": False, "error": "Space key zorunlu"}), 400
    sources = _load_sources()
    if not any(s["key"] == key for s in sources["confluence_spaces"]):
        sources["confluence_spaces"].append({"key": key, "name": name})
        _save_sources(sources)
    return jsonify({"ok": True, "sources": sources})


@app.route("/api/sources/confluence/<key>", methods=["DELETE"])
def sources_confluence_sil(key):
    sources = _load_sources()
    sources["confluence_spaces"] = [s for s in sources["confluence_spaces"] if s["key"] != key]
    _save_sources(sources)
    return jsonify({"ok": True})


@app.route("/api/sources/jira", methods=["POST"])
def sources_jira_ekle():
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip().upper()
    name = (data.get("name") or "").strip() or key
    if not key:
        return jsonify({"ok": False, "error": "Proje key zorunlu"}), 400
    sources = _load_sources()
    if not any(p["key"] == key for p in sources["jira_projects"]):
        sources["jira_projects"].append({"key": key, "name": name})
        _save_sources(sources)
    return jsonify({"ok": True, "sources": sources})


@app.route("/api/sources/jira/<key>", methods=["DELETE"])
def sources_jira_sil(key):
    sources = _load_sources()
    sources["jira_projects"] = [p for p in sources["jira_projects"] if p["key"] != key.upper()]
    _save_sources(sources)
    return jsonify({"ok": True})


@app.route("/api/sources/sync/status")
def sources_sync_durum():
    with _sync_lock:
        return jsonify({
            "running":   _sync_state["running"],
            "log":       list(_sync_state["log"]),
            "last_sync": _sync_state["last_sync"],
            "error":     _sync_state.get("error"),
        })


@app.route("/api/sources/sync", methods=["POST"])
def sources_sync_baslat():
    with _sync_lock:
        if _sync_state["running"]:
            return jsonify({"ok": False, "error": "Zaten çalışıyor"}), 400
        _sync_state.update({"running": True, "log": [], "error": None})

    def _do_sync():
        try:
            env = _env_oku()
            cloud_id = env.get("JIRA_CLOUD_ID", "")
            if not cloud_id:
                raise Exception("Cloud ID bulunamadı. Önce Jira ile Bağlan butonuna tıklayın.")
            sources = _load_sources()

            for space in sources.get("confluence_spaces", []):
                k = space["key"]
                with _sync_lock:
                    _sync_state["log"].append(f"Confluence [{k}] çekiliyor...")
                count = _fetch_confluence_space(k, cloud_id)
                with _sync_lock:
                    _sync_state["log"].append(f"✓ Confluence [{k}]: {count} sayfa")

            for proj in sources.get("jira_projects", []):
                k = proj["key"]
                with _sync_lock:
                    _sync_state["log"].append(f"Jira [{k}] çekiliyor...")
                count, elenen = _fetch_jira_project(k, cloud_id)
                mesaj = f"✓ Jira [{k}]: {count} issue"
                if elenen:
                    mesaj += f" ({elenen} elendi: Backlog/To Do/Cancel)"
                with _sync_lock:
                    _sync_state["log"].append(mesaj)

            last_sync = time.strftime("%d/%m/%Y %H:%M")
            sources["last_sync"] = last_sync
            _save_sources(sources)
            with _sync_lock:
                _sync_state["log"].append(f"✓ Tamamlandı — {last_sync}")
                _sync_state["last_sync"] = last_sync
            logger.info("Veri kaynakları sync tamamlandı.")

        except Exception as e:
            msg = str(e)[:300]
            with _sync_lock:
                _sync_state["log"].append(f"❌ Hata: {msg}")
                _sync_state["error"] = msg
            logger.error(f"Sync hatası: {msg}")
        finally:
            with _sync_lock:
                _sync_state["running"] = False

    threading.Thread(target=_do_sync, daemon=True).start()
    return jsonify({"ok": True})


# ─── Servis Swagger Fetch ─────────────────────────────────────────────────────

@app.route("/api/reference/fetch-be", methods=["POST"])
def reference_fetch_be():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    url  = (data.get("url")  or "").strip()
    auth = (data.get("auth") or "").strip()

    if not name or not url:
        return jsonify({"ok": False, "error": "name ve url zorunlu"}), 400
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({"ok": False, "error": "Geçersiz servis adı (harf/rakam/-/_ kullanın)"}), 400

    headers = {}
    if auth:
        headers["Authorization"] = auth

    try:
        import requests as _req
        resp = _req.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return jsonify({"ok": False, "output": f"HTTP {resp.status_code}: {resp.text[:200]}"})

        SERVIS_DIR.mkdir(parents=True, exist_ok=True)
        hedef = SERVIS_DIR / f"{name}.json"
        try:
            spec = resp.json()
            endpoint_sayisi = len(spec.get("paths", {}))
            hedef.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            boyut = hedef.stat().st_size
            output = f"✓ {name}.json kaydedildi\n  {boyut:,} bytes | {endpoint_sayisi} endpoint"
        except Exception:
            hedef.write_bytes(resp.content)
            output = f"✓ {name}.json kaydedildi ({len(resp.content):,} bytes)"

        logger.info(f"Servis spec alındı: {name} ← {url}")
        return jsonify({"ok": True, "output": output})

    except ImportError:
        return jsonify({"ok": False, "error": "requests paketi yüklü değil: pip install requests"}), 500
    except Exception as e:
        return jsonify({"ok": False, "output": f"Hata: {e}"})


# ─── Bağlam Filtresi ──────────────────────────────────────────────────────────

@app.route("/api/context-filter", methods=["GET"])
def context_filter_oku():
    p = REF_DIR / "context_filter.json"
    if p.exists():
        try:
            return jsonify(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return jsonify({"keywords": [], "jira_keys": [], "confluence_pages": []})


@app.route("/api/context-filter", methods=["POST"])
def context_filter_kaydet():
    data = request.get_json(silent=True) or {}
    filtre = {
        "keywords":         [str(k).strip() for k in data.get("keywords", [])         if str(k).strip()],
        "jira_keys":        [str(k).strip() for k in data.get("jira_keys", [])        if str(k).strip()],
        "confluence_pages": [str(p).strip() for p in data.get("confluence_pages", []) if str(p).strip()],
    }
    p = REF_DIR / "context_filter.json"
    p.write_text(json.dumps(filtre, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Bağlam filtresi güncellendi.")
    return jsonify({"ok": True, "filtre": filtre})


# ─── Jira Ayarları & OAuth ────────────────────────────────────────────────────

JIRA_ENV_KEYS = ["JIRA_CLIENT_ID", "JIRA_CLIENT_SECRET", "JIRA_PROJECT_KEY",
                 "JIRA_URL", "JIRA_CLOUD_ID", "JIRA_ACCESS_TOKEN", "JIRA_REFRESH_TOKEN"]


@app.route("/api/jira/config", methods=["GET"])
def jira_config_oku():
    env = _env_oku()
    return jsonify({
        "client_id":     env.get("JIRA_CLIENT_ID", ""),
        "client_secret": "***" if env.get("JIRA_CLIENT_SECRET") else "",
        "project_key":   env.get("JIRA_PROJECT_KEY", ""),
        "jira_url":      env.get("JIRA_URL", ""),
        "cloud_id":      env.get("JIRA_CLOUD_ID", ""),
        "connected":     bool(env.get("JIRA_ACCESS_TOKEN") and env.get("JIRA_CLOUD_ID")),
    })


@app.route("/api/jira/config", methods=["POST"])
def jira_config_kaydet():
    data = request.get_json(silent=True) or {}
    degisiklikler = {}

    for key, env_key in [("client_id", "JIRA_CLIENT_ID"),
                          ("project_key", "JIRA_PROJECT_KEY"),
                          ("jira_url", "JIRA_URL")]:
        val = data.get(key, "").strip()
        if val:
            degisiklikler[env_key] = val
            os.environ[env_key] = val

    if data.get("client_secret", "").strip() not in ("", "***"):
        v = data["client_secret"].strip()
        degisiklikler["JIRA_CLIENT_SECRET"] = v
        os.environ["JIRA_CLIENT_SECRET"] = v

    if degisiklikler:
        _env_yaz(degisiklikler)
        logger.info(f"Jira config güncellendi: {list(degisiklikler.keys())}")

    return jsonify({"ok": True})


@app.route("/api/jira/auth-url", methods=["POST"])
def jira_auth_url():
    """OAuth URL'ini döndür."""
    try:
        from jira_auth import auth_url_olustur
        url = auth_url_olustur()
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/jira/callback")
def jira_callback():
    """Atlassian OAuth callback — code'u token'a çevirir."""
    code = request.args.get("code", "")
    error = request.args.get("error", "")

    if error:
        logger.error(f"Jira OAuth hatası: {error}")
        return f"""<!DOCTYPE html><html><head><meta charset=UTF-8></head><body style='font-family:sans-serif;text-align:center;padding:50px;background:#0f1117;color:#e2e8f0'>
<h2 style='color:#ef4444'>Yetkilendirme Başarısız</h2>
<p>{error}</p>
<p><a href='http://localhost:5002' style='color:#6366f1'>Uygulamaya Dön</a></p>
</body></html>"""

    if not code:
        return "Kod eksik", 400

    try:
        from jira_auth import auth_tamamla
        result = auth_tamamla(code)
        cloud_name = result.get("cloud_name", "")
        logger.info(f"Jira OAuth tamamlandı — Cloud: {cloud_name}")
        return f"""<!DOCTYPE html><html><head><meta charset=UTF-8></head><body style='font-family:sans-serif;text-align:center;padding:50px;background:#0f1117;color:#e2e8f0'>
<h2 style='color:#22c55e'>Jira Bağlantısı Başarılı!</h2>
<p>Instance: <strong>{cloud_name}</strong></p>
<p style='margin-top:20px'><a href='http://localhost:5002' style='color:#6366f1'>Uygulamaya Dön</a></p>
<script>setTimeout(()=>window.close(),3000)</script>
</body></html>"""
    except Exception as e:
        logger.error(f"Jira token alma hatası: {e}")
        return f"""<!DOCTYPE html><html><head><meta charset=UTF-8></head><body style='font-family:sans-serif;text-align:center;padding:50px;background:#0f1117;color:#e2e8f0'>
<h2 style='color:#ef4444'>Token Alınamadı</h2>
<p>{e}</p>
<p><a href='http://localhost:5002' style='color:#6366f1'>Uygulamaya Dön</a></p>
</body></html>"""


@app.route("/api/jira/test", methods=["POST"])
def jira_test():
    """Jira bağlantısını test et."""
    try:
        env = _env_oku()
        statik_eksik = [k for k in ("JIRA_CLIENT_ID", "JIRA_CLIENT_SECRET", "JIRA_URL", "JIRA_PROJECT_KEY") if not env.get(k)]
        if statik_eksik:
            return jsonify({"ok": False, "error": f"Jira ayarları eksik: {', '.join(statik_eksik)}. Doldurup Kaydet'e basın."}), 400
        oauth_eksik = [k for k in ("JIRA_ACCESS_TOKEN", "JIRA_CLOUD_ID") if not env.get(k)]
        if oauth_eksik:
            return jsonify({"ok": False, "error": "OAuth bağlantısı tamamlanmamış. 'Jira ile Bağlan' butonuna tıklayın."}), 400
        from jira_agent import jira_auth_test
        if jira_auth_test():
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Jira bağlantısı başarısız. 'Jira ile Bağlan' ile yeniden yetkilendirin."}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Jira Task Hiyerarşisi ────────────────────────────────────────────────────

def _jira_baglanti_eksik() -> str | None:
    """Jira bağlantı env değişkenlerini kontrol eder; eksikse hata metni döndürür."""
    env = _env_oku()
    eksik = [k for k in ("JIRA_ACCESS_TOKEN", "JIRA_CLOUD_ID", "JIRA_PROJECT_KEY") if not env.get(k)]
    return f"Jira bağlantısı eksik: {', '.join(eksik)}" if eksik else None


@app.route("/api/jira/hierarchy/preview", methods=["POST"])
def jira_hierarchy_onizleme():
    """1. Adım — AI hiyerarşi önerisi üretir; Jira'ya YAZMAZ.

    Analist dönen öneriyi ekranda görüp seçim yapar, sonra /create çağrılır.
    """
    data = request.get_json(silent=True) or {}
    dosya = (data.get("dosya") or "teknik-analiz.md").strip()

    if ".." in dosya or "/" in dosya or "\\" in dosya:
        return jsonify({"ok": False, "error": "Geçersiz dosya adı"}), 400

    hata = _jira_baglanti_eksik()
    if hata:
        return jsonify({"ok": False, "error": hata}), 400

    try:
        from skills.jira_tasks import jira_hiyerarsi_uret
        sonuc = jira_hiyerarsi_uret(teknik_analiz_dosya=dosya)
        return jsonify({"ok": True, **sonuc})
    except Exception as e:
        logger.error(f"Jira hiyerarşi önizleme hatası: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/jira/hierarchy/create", methods=["POST"])
def jira_hierarchy_olustur():
    """2. Adım — Analistin seçtiği/düzenlediği hiyerarşiyi Jira'da oluşturur."""
    data = request.get_json(silent=True) or {}
    hierarchy = data.get("hierarchy")
    confluence_url = (data.get("confluence_url") or "").strip() or None

    if not isinstance(hierarchy, dict):
        return jsonify({"ok": False, "error": "Geçersiz hiyerarşi verisi"}), 400

    hata = _jira_baglanti_eksik()
    if hata:
        return jsonify({"ok": False, "error": hata}), 400

    try:
        from skills.jira_tasks import jira_hiyerarsi_olustur
        sonuc = jira_hiyerarsi_olustur(hierarchy, confluence_url=confluence_url)
        return jsonify({"ok": True, **sonuc})
    except Exception as e:
        logger.error(f"Jira hiyerarşi oluşturma hatası: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Confluence Yayımla ───────────────────────────────────────────────────────

@app.route("/api/confluence/publish", methods=["POST"])
def confluence_yayimla_route():
    data = request.get_json(silent=True) or {}
    dosya_adi = (data.get("dosya") or "").strip()
    space_key = (data.get("space_key") or "").strip()
    title     = (data.get("title") or "").strip() or None
    parent_id = (data.get("parent_id") or "").strip() or None

    if not dosya_adi:
        return jsonify({"ok": False, "error": "dosya parametresi zorunlu"}), 400
    if not space_key:
        return jsonify({"ok": False, "error": "space_key parametresi zorunlu"}), 400

    # Path traversal koruması
    if ".." in dosya_adi or "/" in dosya_adi or "\\" in dosya_adi:
        return jsonify({"ok": False, "error": "Geçersiz dosya adı"}), 400
    hedef = OUTPUT_DIR / dosya_adi
    if not hedef.exists():
        return jsonify({"ok": False, "error": "Dosya bulunamadı"}), 404

    env = _env_oku()
    cloud_id = env.get("JIRA_CLOUD_ID", "")
    if not cloud_id:
        return jsonify({"ok": False, "error": "Cloud ID bulunamadı. Jira ile bağlanın."}), 400

    try:
        from skills.confluence_yaz import confluence_yayimla
        result = confluence_yayimla(dosya_adi, space_key, cloud_id, title, parent_id)
        return jsonify({"ok": True, **result})
    except Exception as e:
        logger.error(f"Confluence yayımlama hatası: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Confluence Diagnostik ───────────────────────────────────────────────────

@app.route("/api/confluence/diagnose", methods=["GET"])
def confluence_diagnose():
    """
    Mevcut access token'ın Confluence scope'larını ve erişimini kontrol eder.
    Kullanıcıya hangi izinlerin olup olmadığını gösterir.
    """
    import requests as _req
    env = _env_oku()
    token = env.get("JIRA_ACCESS_TOKEN", "")
    if not token:
        return jsonify({"ok": False, "error": "Access token bulunamadı. Jira ile bağlanın."}), 400

    sonuc = {"ok": True, "token_var": True}

    # 1. Accessible resources → hangi scope'lar var?
    try:
        r = _req.get(
            "https://api.atlassian.com/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            resources = r.json()
            sonuc["resources"] = resources
            # Confluence scope kontrolü
            conf_scopes = []
            for res in resources:
                scopes = res.get("scopes", [])
                conf_scopes = [s for s in scopes if "confluence" in s.lower()]
                if conf_scopes:
                    break
            sonuc["confluence_scopes"] = conf_scopes
            sonuc["confluence_erisim"] = bool(conf_scopes)
            if not conf_scopes:
                sonuc["tavsiye"] = (
                    "Token'da Confluence scope'u yok. "
                    "developer.atlassian.com → Uygulamanız → Permissions → Confluence API ekleyin, "
                    "ardından Ayarlar'dan yeniden yetkilendirin."
                )
        else:
            sonuc["accessible_resources_hata"] = f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        sonuc["accessible_resources_hata"] = str(e)

    # 2. v2 API ile Confluence testi (uygulamanın kullandığı endpoint)
    cloud_id = env.get("JIRA_CLOUD_ID", "")
    if cloud_id:
        for test_path, test_label in [
            ("/wiki/api/v2/spaces?limit=1", "v2 spaces (read:space:confluence)"),
            ("/wiki/api/v2/pages?limit=1", "v2 pages (read:page:confluence)"),
        ]:
            try:
                rt = _req.get(
                    f"https://api.atlassian.com/ex/confluence/{cloud_id}{test_path}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=15,
                )
                try:
                    body = rt.json()
                except Exception:
                    body = rt.text[:300]
                sonuc.setdefault("confluence_api_testler", {})[test_label] = {
                    "status": rt.status_code,
                    "ok": rt.status_code == 200,
                    "yanit": body,
                }
            except Exception as e:
                sonuc.setdefault("confluence_api_testler", {})[test_label] = {"ok": False, "hata": str(e)}
    else:
        sonuc["confluence_api_testler"] = {"hata": "JIRA_CLOUD_ID bulunamadı"}

    return jsonify(sonuc)


# ─── HTML Prototip ────────────────────────────────────────────────────────────

@app.route("/api/mockup/generate", methods=["POST"])
def mockup_generate():
    surec_dosya = OUTPUT_DIR / "surec-analizi.md"
    if not surec_dosya.exists():
        return jsonify({"ok": False, "error": "surec-analizi.md bulunamadı. Önce süreç analizi yapın."}), 400
    try:
        from skills.html_mockup import html_mockup_uret
        yol = html_mockup_uret()
        return jsonify({"ok": True, "dosya": yol.name, "boyut": yol.stat().st_size})
    except Exception as e:
        logger.error(f"Mockup üretim hatası: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Git Güncellemeleri ──────────────────────────────────────────────────────

_git_lock = threading.Lock()


def _git_calistir(args: list[str], timeout: int = 30) -> dict:
    """Git komutu çalıştır. Return: {ok, stdout, stderr, returncode}."""
    try:
        sonuc = subprocess.run(
            ["git"] + args,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": sonuc.returncode == 0,
            "stdout": sonuc.stdout.strip(),
            "stderr": sonuc.stderr.strip(),
            "returncode": sonuc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Zaman aşımı ({timeout}s)", "returncode": -1}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "git komutu bulunamadı (Xcode Command Line Tools yüklü mü?)", "returncode": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "returncode": -1}


@app.route("/api/git/status", methods=["GET"])
def git_status():
    """Mevcut commit, branch ve uzak depo ile fark bilgisini döndür."""
    if not (BASE_DIR / ".git").exists():
        return jsonify({"ok": False, "error": "Bu dizin bir git deposu değil."}), 400

    branch = _git_calistir(["rev-parse", "--abbrev-ref", "HEAD"])
    mevcut = _git_calistir(["log", "-1", "--pretty=format:%h|%s|%ci|%an"])
    yerel_degisiklik = _git_calistir(["status", "--porcelain"])

    # Uzak ile karşılaştırmak için fetch
    fetch_yap = request.args.get("fetch", "false").lower() in ("1", "true", "yes")
    fetch_sonuc = None
    if fetch_yap:
        fetch_sonuc = _git_calistir(["fetch", "origin"], timeout=60)

    # ahead/behind hesabı
    branch_adi = branch["stdout"] if branch["ok"] else "main"
    sayim = _git_calistir(["rev-list", "--left-right", "--count", f"HEAD...origin/{branch_adi}"])
    ahead, behind = 0, 0
    if sayim["ok"] and "\t" in sayim["stdout"]:
        try:
            a, b = sayim["stdout"].split("\t")
            ahead, behind = int(a), int(b)
        except ValueError:
            pass

    # Uzak son commit
    uzak = _git_calistir(["log", "-1", f"origin/{branch_adi}", "--pretty=format:%h|%s|%ci|%an"])

    mevcut_parsed = {}
    if mevcut["ok"] and "|" in mevcut["stdout"]:
        h, s, c, a = mevcut["stdout"].split("|", 3)
        mevcut_parsed = {"hash": h, "mesaj": s, "tarih": c, "yazar": a}

    uzak_parsed = {}
    if uzak["ok"] and "|" in uzak["stdout"]:
        h, s, c, a = uzak["stdout"].split("|", 3)
        uzak_parsed = {"hash": h, "mesaj": s, "tarih": c, "yazar": a}

    return jsonify({
        "ok": True,
        "branch": branch_adi,
        "mevcut": mevcut_parsed,
        "uzak": uzak_parsed,
        "ahead": ahead,
        "behind": behind,
        "kirli": bool(yerel_degisiklik["stdout"]),
        "fetch": fetch_sonuc,
        "guncelleme_var": behind > 0,
    })


@app.route("/api/git/pull", methods=["POST"])
@admin_gerekli
def git_pull():
    """git fetch + git pull origin <branch>."""
    if not _git_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "Güncelleme zaten çalışıyor."}), 409

    try:
        if not (BASE_DIR / ".git").exists():
            return jsonify({"ok": False, "error": "Bu dizin bir git deposu değil."}), 400

        # Yerel değişiklik varsa güvenli olmak için reddet
        kirli = _git_calistir(["status", "--porcelain"])
        if kirli["stdout"]:
            return jsonify({
                "ok": False,
                "error": "Yerel değişiklikler var. Önce kaydedin veya geri alın.",
                "detay": kirli["stdout"][:1000],
            }), 400

        branch = _git_calistir(["rev-parse", "--abbrev-ref", "HEAD"])
        branch_adi = branch["stdout"] if branch["ok"] else "main"

        # Fetch + pull
        fetch_r = _git_calistir(["fetch", "origin"], timeout=60)
        if not fetch_r["ok"]:
            return jsonify({"ok": False, "error": "Fetch başarısız", "detay": fetch_r["stderr"]}), 500

        # ff-only: merge yapılmasını engelle, conflict riski olursa kullanıcıya bildir
        pull_r = _git_calistir(["pull", "--ff-only", "origin", branch_adi], timeout=60)
        if not pull_r["ok"]:
            return jsonify({
                "ok": False,
                "error": "Pull başarısız (fast-forward yapılamıyor — manuel müdahale gerekli olabilir)",
                "detay": pull_r["stderr"] or pull_r["stdout"],
            }), 500

        # requirements.txt değişti mi kontrol
        son = _git_calistir(["log", "-1", "--pretty=format:%h|%s"])
        deps_degisti = "requirements.txt" in _git_calistir(["diff", "--name-only", "HEAD@{1}", "HEAD"])["stdout"]

        return jsonify({
            "ok": True,
            "mesaj": "Güncelleme tamamlandı. Değişikliklerin etkili olması için uygulamayı yeniden başlatın.",
            "son_commit": son["stdout"],
            "deps_degisti": deps_degisti,
            "pull_ciktisi": pull_r["stdout"],
        })
    finally:
        _git_lock.release()


@app.after_request
def guvenlik_basliklari(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data:;"
    )
    return response


@app.errorhandler(413)
def request_too_large(e):
    return jsonify({"error": f"Dosya çok büyük — maksimum {app.config['MAX_CONTENT_LENGTH'] // 1024 // 1024} MB kabul edilir"}), 413


def _baslangic_guvenlik_kontrol(host: str, auth_aktif: bool) -> bool:
    """Güvenli olmayan kurulum senaryolarını engeller.

    - LAN'a açık + auth kapalı = ağdaki herkes anonim erişebilir
    - Override: ALLOW_LAN_NO_AUTH=true (kullanıcı bilerek istiyorsa)
    """
    lan_acik = host not in ("127.0.0.1", "localhost", "::1")
    override = os.getenv("ALLOW_LAN_NO_AUTH", "false").lower() in ("1", "true", "yes")

    if lan_acik and not auth_aktif:
        if override:
            logger.warning("=" * 72)
            logger.warning("⚠ GÜVENLİK UYARISI: LAN'a açık + AUTH kapalı")
            logger.warning("  HOST=%s, AUTH_ENABLED=false → ağdaki herkes erişebilir.", host)
            logger.warning("  ALLOW_LAN_NO_AUTH=true ile override edildi — kendi sorumluluğunuzda.")
            logger.warning("=" * 72)
            return True
        print()
        print("=" * 72)
        print("  ⛔ BAŞLANGIÇ ENGELLENDİ — Güvensiz kurulum")
        print("=" * 72)
        print(f"  HOST={host} (LAN'a açık) + AUTH_ENABLED=false")
        print("  Bu kombinasyon ağdaki herkesin uygulamaya anonim erişimine izin verir.")
        print()
        print("  Çözüm seçenekleri (.env dosyasında):")
        print("    1) Sadece kendi makinanız için: HOST=127.0.0.1 (önerilir)")
        print("    2) Ekip kullanımı için:        AUTH_ENABLED=true")
        print("    3) Bilerek riski kabul:        ALLOW_LAN_NO_AUTH=true")
        print("=" * 72)
        return False
    return True


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5002))
    host = os.getenv("HOST", "127.0.0.1")  # Default: yalnız yerel; LAN için .env'de HOST=0.0.0.0

    if not _baslangic_guvenlik_kontrol(host, _auth_aktif_mi()):
        sys.exit(1)

    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    if host == "0.0.0.0":
        logger.info(f"Analyst Studio başlatılıyor → http://localhost:{port}  |  Ağ: http://{local_ip}:{port}")
    else:
        logger.info(f"Analyst Studio başlatılıyor → http://localhost:{port}  (sadece yerel; LAN için .env'de HOST=0.0.0.0)")
    app.run(host=host, port=port, debug=False)
