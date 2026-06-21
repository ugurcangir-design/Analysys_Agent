"""
Jira entegrasyonu — BRD Analyst Agent
OAuth 2.0 token yönetimi, task oluşturma/güncelleme, Markdown→ADF dönüşümü.
"""

import re
import json
import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv, set_key

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
INPUT_DIR  = BASE_DIR / "input"
LOG_DIR    = BASE_DIR / "logs"
ENV_PATH   = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)


# ─── ENV YÖNETİMİ ─────────────────────────────────────────────────────────────

def env_al(key: str) -> str:
    return os.getenv(key, "")

def env_guncelle(key: str, value: str) -> None:
    set_key(str(ENV_PATH), key, value)
    os.environ[key] = value


# ─── BAŞLANGIÇ KONTROLÜ ───────────────────────────────────────────────────────

ZORUNLU = ["JIRA_CLIENT_ID", "JIRA_CLIENT_SECRET", "JIRA_ACCESS_TOKEN",
           "JIRA_REFRESH_TOKEN", "JIRA_CLOUD_ID", "JIRA_PROJECT_KEY"]

def baslangic_kontrol() -> bool:
    eksikler = [k for k in ZORUNLU if not env_al(k)]
    if eksikler:
        print(f"HATA: Jira config eksik: {', '.join(eksikler)}")
        print("Önce Ayarlar sekmesinden Jira'ya bağlanın.")
        return False
    return True


# ─── TOKEN YÖNETİMİ ───────────────────────────────────────────────────────────

def token_yenile() -> bool:
    refresh = env_al("JIRA_REFRESH_TOKEN")
    cid     = env_al("JIRA_CLIENT_ID")
    csec    = env_al("JIRA_CLIENT_SECRET")
    if not all([refresh, cid, csec]):
        return False
    try:
        r = requests.post(
            "https://auth.atlassian.com/oauth/token",
            json={"grant_type": "refresh_token", "client_id": cid,
                  "client_secret": csec, "refresh_token": refresh},
            timeout=30,
        )
        if r.status_code != 200:
            return False
        d = r.json()
        if not d.get("access_token"):
            return False
        env_guncelle("JIRA_ACCESS_TOKEN", d["access_token"])
        if d.get("refresh_token"):
            env_guncelle("JIRA_REFRESH_TOKEN", d["refresh_token"])
        print("✓ Jira access token yenilendi.")
        return True
    except Exception:
        return False


def _headers() -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {env_al('JIRA_ACCESS_TOKEN')}",
    }

def _base_url() -> str:
    return f"https://api.atlassian.com/ex/jira/{env_al('JIRA_CLOUD_ID')}"


def jira_istegi_at(method: str, endpoint: str, **kwargs):
    url = _base_url() + endpoint
    for deneme in range(2):
        try:
            r = requests.request(method, url, headers=_headers(), timeout=30, **kwargs)
            if r.status_code == 401 and deneme == 0:
                if token_yenile():
                    continue
                return None
            return r
        except requests.exceptions.Timeout:
            print(f"HATA: İstek zaman aşımı ({endpoint})")
            return None
        except Exception as e:
            print(f"HATA: {type(e).__name__}: {e}")
            return None
    return None


# ─── BAĞLANTI TESTİ ───────────────────────────────────────────────────────────

def jira_auth_test() -> bool:
    r = jira_istegi_at("GET", "/rest/api/3/myself")
    if r and r.status_code == 200:
        d = r.json()
        print(f"✓ Jira bağlantısı OK — {d.get('displayName', '')} ({d.get('emailAddress', '')})")
        return True
    print(f"HATA: Jira bağlantısı başarısız: {r.status_code if r else 'bağlantı yok'}")
    return False


# ─── DOSYA YARDIMCIları ───────────────────────────────────────────────────────

def input_dosya_adini_al() -> str | None:
    for pat in ["*.pdf", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.md", "*.txt", "*.docx"]:
        dosyalar = sorted(f for f in INPUT_DIR.glob(pat) if f.stat().st_size > 0)
        if dosyalar:
            return dosyalar[0].stem
    return None

def teknik_analizi_oku() -> str | None:
    p = OUTPUT_DIR / "teknik-analiz.md"
    if not p.exists():
        print("HATA: teknik-analiz.md bulunamadı.")
        return None
    return p.read_text(encoding="utf-8")

def sonuc_dosyasi_yolu() -> Path:
    return OUTPUT_DIR / "jira-sonuc.txt"

def sonuc_dosyasini_oku() -> str | None:
    p = sonuc_dosyasi_yolu()
    if not p.exists():
        return None
    for satir in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^Task\s*:\s*(.*)", satir)
        if m:
            return m.group(1).strip()
    return None

def sonuc_dosyasina_yaz(task_key: str, task_basligi: str) -> None:
    jira_url = env_al("JIRA_URL") or "https://yourcompany.atlassian.net"
    sonuc_dosyasi_yolu().write_text(
        f"Task  : {task_key}\n"
        f"Baslik: {task_basligi}\n"
        f"Link  : {jira_url}/browse/{task_key}\n"
        f"Tarih : {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )

def log_yaz(mesaj: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    p = LOG_DIR / f"log-{time.strftime('%Y-%m-%d')}.txt"
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {mesaj}\n")


# ─── TASK BAŞLIĞI ─────────────────────────────────────────────────────────────

def task_basligi_uret(dosya_adi: str) -> str:
    stem = re.sub(r"[-_\.]+", " ", Path(dosya_adi).stem if dosya_adi else "").strip()
    stem = re.sub(r"\s+", " ", stem).title()
    if len(stem) < 3:
        stem = "Teknik Analiz"
    return f"BE - {stem}"[:100]


# ─── MARKDOWN → ADF ───────────────────────────────────────────────────────────

def parse_inline(text: str) -> list:
    nodes = []
    pos = 0
    while pos < len(text):
        remaining = text[pos:]

        m = re.match(r'\*\*(.+?)\*\*', remaining, re.DOTALL)
        if m:
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "strong"}]})
            pos += m.end(); continue

        m = re.match(r'\*([^*\n]+?)\*', remaining, re.DOTALL)
        if m:
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "em"}]})
            pos += m.end(); continue

        m = re.match(r'_([^_\n]+?)_', remaining, re.DOTALL)
        if m:
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "em"}]})
            pos += m.end(); continue

        m = re.match(r'`(.+?)`', remaining, re.DOTALL)
        if m:
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "code"}]})
            pos += m.end(); continue

        m = re.match(r'\[([^\]]+)\]\((https?://[^\)]+)\)', remaining)
        if m:
            nodes.append({"type": "text", "text": m.group(1),
                          "marks": [{"type": "link", "attrs": {"href": m.group(2)}}]})
            pos += m.end(); continue

        m = re.match(r'(.+?)(?=\*\*|\*|_|`|\[|$)', remaining, re.DOTALL)
        if m and m.group(1):
            nodes.append({"type": "text", "text": m.group(1)})
            pos += m.end(); continue

        if pos < len(text):
            nodes.append({"type": "text", "text": text[pos:]}); break

    return nodes or [{"type": "text", "text": text}]


def _p(text: str) -> dict:
    return {"type": "paragraph", "content": parse_inline(text)}

def _h(text: str, level: int) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": parse_inline(text)}

def _rule() -> dict:
    return {"type": "rule"}

def _bullet(items: list) -> dict:
    return {"type": "bulletList",
            "content": [{"type": "listItem", "content": [_p(i)]} for i in items]}

def _ordered(items: list) -> dict:
    return {"type": "orderedList",
            "content": [{"type": "listItem", "content": [_p(i)]} for i in items]}

def _code(code: str, lang: str = "") -> dict:
    return {"type": "codeBlock", "attrs": {"language": lang},
            "content": [{"type": "text", "text": code}]}

def _is_table(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|")

def _is_sep(line: str) -> bool:
    return _is_table(line) and re.match(r'^[\|\s\-:]+$', line.strip())

def _parse_row(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]

def _table(rows: list) -> dict:
    adf_rows = []
    for i, row in enumerate(rows):
        ct = "tableHeader" if i == 0 else "tableCell"
        adf_rows.append({"type": "tableRow",
            "content": [{"type": ct, "attrs": {}, "content": [_p(c)]} for c in row]})
    return {"type": "table",
            "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
            "content": adf_rows}


def markdown_to_adf(md: str) -> list:
    # HTML yorumlarını (<!-- ... -->) at — markdown'da görünmez olmaları beklenir,
    # ama ADF'te paragraf olarak literal yazıya dönüşüp Jira description'ında
    # görünür hale gelirler (örn. jira_gorevleri'nin RAG meta yorumu). Tek/çok
    # satırlı tüm yorumları temizle.
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    lines = md.split("\n")
    nodes = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1; continue

        if re.match(r'^-{3,}$', s) or re.match(r'^={3,}$', s):
            nodes.append(_rule()); i += 1; continue

        if s.startswith("```"):
            lang = s[3:].strip(); code_lines = []; i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i]); i += 1
            nodes.append(_code("\n".join(code_lines), lang)); i += 1; continue

        m = re.match(r'^(#{1,6})\s+(.*)', s)
        if m:
            nodes.append(_h(m.group(2), min(len(m.group(1)), 6))); i += 1; continue

        if _is_table(s):
            header = _parse_row(s); i += 1; table_rows = []
            if i < len(lines) and _is_sep(lines[i]): i += 1
            while i < len(lines) and _is_table(lines[i].strip()):
                table_rows.append(_parse_row(lines[i])); i += 1
            if header: nodes.append(_table([header] + table_rows)); continue

        if re.match(r'^[-*]\s+', s):
            items = []
            while i < len(lines) and re.match(r'^[-*]\s+', lines[i].strip()):
                items.append(re.sub(r'^[-*]\s+', '', lines[i].strip())); i += 1
            nodes.append(_bullet(items)); continue

        if re.match(r'^\d+\.\s+', s):
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i].strip()):
                items.append(re.sub(r'^\d+\.\s+', '', lines[i].strip())); i += 1
            nodes.append(_ordered(items)); continue

        nodes.append(_p(s)); i += 1

    return nodes


# ─── JIRA İŞLEMLERİ ───────────────────────────────────────────────────────────

def jira_task_olustur(summary: str, teknik_analiz: str) -> str | None:
    payload = {
        "fields": {
            "project": {"key": env_al("JIRA_PROJECT_KEY")},
            "summary": summary,
            "description": {"type": "doc", "version": 1,
                            "content": markdown_to_adf(teknik_analiz)},
            "issuetype": {"name": "Task"},
        }
    }
    r = jira_istegi_at("POST", "/rest/api/3/issue", json=payload)
    if r and r.status_code in (200, 201):
        key = r.json()["key"]
        log_yaz(f"Task oluşturuldu: {key} - {summary}")
        return key
    print(f"HATA: Task oluşturulamadı: {r.status_code if r else 'bağlantı yok'}")
    if r: print(f"  Detay: {r.text[:200]}")
    log_yaz(f"Task oluşturma hatası: {r.status_code if r else 'n/a'}")
    return None


def jira_task_guncelle(task_key: str, summary: str, teknik_analiz: str) -> bool:
    payload = {
        "fields": {
            "summary": summary,
            "description": {"type": "doc", "version": 1,
                            "content": markdown_to_adf(teknik_analiz)},
        }
    }
    r = jira_istegi_at("PUT", f"/rest/api/3/issue/{task_key}", json=payload)
    if r and r.status_code == 204:
        log_yaz(f"Task güncellendi: {task_key}")
        return True
    print(f"HATA: Güncelleme başarısız: {r.status_code if r else 'n/a'}")
    if r: print(f"  Detay: {r.text[:200]}")
    return False


# ─── MAIN (run.py tarafından çağrılır) ────────────────────────────────────────

def main() -> tuple[str, str]:
    """
    Teknik analizi Jira'ya gönderir.
    Returns: (task_key, task_basligi)
    """
    if not baslangic_kontrol():
        raise RuntimeError("Jira yapılandırması eksik.")

    if not jira_auth_test():
        raise RuntimeError("Jira bağlantısı başarısız.")

    teknik_analiz = teknik_analizi_oku()
    if not teknik_analiz:
        raise FileNotFoundError("teknik-analiz.md bulunamadı.")

    dosya_adi = input_dosya_adini_al()
    task_basligi = task_basligi_uret(dosya_adi or "analiz")

    mevcut_key = sonuc_dosyasini_oku()
    if mevcut_key:
        print(f"Mevcut task güncelleniyor: {mevcut_key}...")
        if not jira_task_guncelle(mevcut_key, task_basligi, teknik_analiz):
            raise RuntimeError("Jira task güncellenemedi.")
        task_key = mevcut_key
    else:
        print("Yeni task oluşturuluyor...")
        task_key = jira_task_olustur(task_basligi, teknik_analiz)
        if not task_key:
            raise RuntimeError("Jira task oluşturulamadı.")

    sonuc_dosyasina_yaz(task_key, task_basligi)
    jira_url = env_al("JIRA_URL") or "https://yourcompany.atlassian.net"
    print(f"✓ Jira task: {task_key} — {jira_url}/browse/{task_key}")
    return task_key, task_basligi
