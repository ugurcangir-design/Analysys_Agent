"""
Flask web sunucusu — BRD Analyst Agent (port 5002)
"""

import os
import sys
import json
import time
import signal
import shutil
import logging
import zipfile
import subprocess
import threading
import tempfile
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, send_file, abort, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

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

LOG_FILE = LOG_DIR / f"app-{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# SECRET_KEY: .env'den alınır, yoksa rastgele üretilir (sunucu yeniden başlayınca oturumlar sıfırlanır)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(32)

# Kullanıcı veritabanı — root dizinde, git'e gitmez
USERS_PATH = BASE_DIR / "users.json"

# Auth gerektirmeyen route'lar
AUTH_MUAF = {"/login", "/api/auth/login"}


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


def _atlassian_refresh() -> str:
    """Access token'ı yenile, yeni token döndür."""
    import requests as _req
    env = _env_oku()
    refresh = env.get("JIRA_REFRESH_TOKEN", "")
    if not refresh:
        raise Exception("Refresh token yok. Jira ile yeniden bağlanın.")
    r = _req.post("https://auth.atlassian.com/oauth/token", json={
        "grant_type": "refresh_token",
        "client_id": env.get("JIRA_CLIENT_ID", ""),
        "client_secret": env.get("JIRA_CLIENT_SECRET", ""),
        "refresh_token": refresh,
    }, timeout=15)
    tokens = r.json()
    if "access_token" not in tokens:
        raise Exception(tokens.get("error_description", "Token yenilenemedi"))
    _env_yaz({"JIRA_ACCESS_TOKEN": tokens["access_token"]})
    if "refresh_token" in tokens:
        _env_yaz({"JIRA_REFRESH_TOKEN": tokens["refresh_token"]})
    os.environ["JIRA_ACCESS_TOKEN"] = tokens["access_token"]
    return tokens["access_token"]


def _atlassian_get(path: str, cloud_id: str, service: str = "jira") -> dict:
    import requests as _req
    env = _env_oku()
    token = env.get("JIRA_ACCESS_TOKEN", "")
    base = f"https://api.atlassian.com/ex/{service}/{cloud_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    r = _req.get(base + path, headers=headers, timeout=30)
    if r.status_code == 401:
        try:
            token = _atlassian_refresh()
        except Exception as refresh_err:
            raise Exception(f"Yetkilendirme başarısız. Ayarlar → Jira ile yeniden bağlanın. ({refresh_err})")
        headers["Authorization"] = f"Bearer {token}"
        r = _req.get(base + path, headers=headers, timeout=30)
    if r.status_code == 401:
        detail = ""
        try:
            detail = r.json().get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        logger.warning(f"Atlassian 401 [{service}] path={path} → {detail}")
        if service == "confluence":
            raise Exception(
                "Confluence erişimi reddedildi (401). "
                "Ayarlar → 'Confluence Bağlantısını Test Et' butonuyla hangi izinlerin eksik olduğunu görebilirsiniz. "
                f"Atlassian yanıtı: {detail}"
            )
        raise Exception(f"Atlassian API 401: {detail}")
    r.raise_for_status()
    return r.json()


def _atlassian_post(path: str, body: dict, cloud_id: str, service: str = "jira") -> dict:
    import requests as _req
    env = _env_oku()
    token = env.get("JIRA_ACCESS_TOKEN", "")
    base = f"https://api.atlassian.com/ex/{service}/{cloud_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
               "Content-Type": "application/json"}
    r = _req.post(base + path, json=body, headers=headers, timeout=30)
    if r.status_code == 401:
        token = _atlassian_refresh()
        headers["Authorization"] = f"Bearer {token}"
        r = _req.post(base + path, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


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


def _fetch_jira_project(project_key: str, cloud_id: str) -> int:
    JIRA_REF_DIR.mkdir(parents=True, exist_ok=True)
    issues, next_token = [], None
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
            desc = f.get("description") or ""
            if isinstance(desc, dict):
                desc = _adf_to_text(desc)
            issues.append({
                "key": issue["key"],
                "summary": f.get("summary", ""),
                "status": (f.get("status") or {}).get("name", ""),
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
    return len(issues)


# Heartbeat takibi
_son_heartbeat = time.time()
_heartbeat_lock = threading.Lock()
_suspended = False          # True → tarayıcı 2+ dakikadır bağlı değil
_process: subprocess.Popen | None = None
_process_lock = threading.Lock()

SUSPEND_SURE = 60           # saniye — bu kadar heartbeat gelmezse uyku
DESKTOP_MODE = os.getenv("DESKTOP_MODE", "false").lower() in ("1", "true", "yes")


def _heartbeat_izle():
    global _suspended
    while True:
        time.sleep(10)
        with _heartbeat_lock:
            gecen = time.time() - _son_heartbeat
        _suspended = gecen > SUSPEND_SURE
        # Desktop modunda: uyku sonrası 30 saniye daha beklenir, ardından kapat
        if DESKTOP_MODE and gecen > SUSPEND_SURE + 30:
            logger.info("Desktop modu: tarayıcı bağlantısı kesildi, uygulama kapatılıyor.")
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
        )

    def _bekle():
        global _process
        try:
            out, _ = _process.communicate(timeout=600)
            logger.info(f"[{mod}] çıktı:\n{out}")
        except subprocess.TimeoutExpired:
            _process.kill()
            logger.error(f"[{mod}] zaman aşımı.")
        except Exception as e:
            logger.error(f"[{mod}] beklenmeyen hata: {e}")

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
        guncel = subprocess.check_output(
            ["git", "fetch", "--dry-run"], cwd=BASE_DIR, stderr=subprocess.STDOUT, text=True
        )
        return jsonify({"hash": hash_, "mesaj": mesaj, "tarih": tarih[:19], "hata": None})
    except Exception as e:
        return jsonify({"hash": "?", "mesaj": "Git bilgisi alınamadı", "tarih": "", "hata": str(e)})


@app.route("/api/update", methods=["POST"])
def guncelle():
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

    # Düzeltme notunu geçici dosyaya yaz
    import tempfile
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
            import os as _os
            try:
                _os.unlink(tmp_yol)
            except Exception:
                pass

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


def _env_oku() -> dict:
    """Mevcut .env dosyasını key→value dict olarak oku."""
    env_yol = BASE_DIR / ".env"
    sonuc = {}
    if env_yol.exists():
        for satir in env_yol.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if satir and not satir.startswith("#") and "=" in satir:
                k, _, v = satir.partition("=")
                sonuc[k.strip()] = v.strip().strip("'\"")
    return sonuc


def _env_yaz(degiskenler: dict) -> None:
    """Mevcut .env'i koru, sadece belirtilen anahtarları güncelle/ekle."""
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

    env_yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")


def _maskele(deger: str) -> str:
    if not deger or len(deger) < 8:
        return "***"
    return deger[:6] + "..." + deger[-4:]


def _claude_cli_var_mi() -> bool:
    import shutil as _shutil
    return bool(_shutil.which("claude"))


# ─── Auth Route'ları ──────────────────────────────────────────────────────────

@app.route("/login")
def login_sayfasi():
    if _giris_yapildi_mi():
        return redirect("/")
    return render_template("login.html")


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
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
                count = _fetch_jira_project(k, cloud_id)
                with _sync_lock:
                    _sync_state["log"].append(f"✓ Jira [{k}]: {count} issue")

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
    import re as _re
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    url  = (data.get("url")  or "").strip()
    auth = (data.get("auth") or "").strip()

    if not name or not url:
        return jsonify({"ok": False, "error": "name ve url zorunlu"}), 400
    if not _re.match(r'^[a-zA-Z0-9_-]+$', name):
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

@app.route("/api/jira/hierarchy", methods=["POST"])
def jira_hierarchy_olustur():
    data = request.get_json(silent=True) or {}
    confluence_url = (data.get("confluence_url") or "").strip() or None
    dosya = (data.get("dosya") or "teknik-analiz.md").strip()

    if ".." in dosya or "/" in dosya or "\\" in dosya:
        return jsonify({"ok": False, "error": "Geçersiz dosya adı"}), 400

    env = _env_oku()
    eksik = [k for k in ("JIRA_ACCESS_TOKEN", "JIRA_CLOUD_ID", "JIRA_PROJECT_KEY") if not env.get(k)]
    if eksik:
        return jsonify({"ok": False, "error": f"Jira bağlantısı eksik: {', '.join(eksik)}"}), 400

    try:
        from skills.jira_tasks import jira_tasks_olustur
        sonuc = jira_tasks_olustur(teknik_analiz_dosya=dosya, confluence_url=confluence_url)
        return jsonify({"ok": True, **sonuc})
    except Exception as e:
        logger.error(f"Jira hiyerarşi hatası: {e}")
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5002))
    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    logger.info(f"BRD Analyst Agent başlatılıyor → http://localhost:{port}  |  Ağ: http://{local_ip}:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
