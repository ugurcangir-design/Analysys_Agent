"""
Atlassian API yardımcıları — token yenileme, HTTP get/post, Confluence CRUD.
skills/ içindeki tüm Atlassian işlemleri buradan yapılır.
"""

import logging
import os
import urllib.parse
import requests as _req
from pathlib import Path
from dotenv import load_dotenv, set_key

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


# ─── Env Okuma ────────────────────────────────────────────────────────────────

def env_oku() -> dict:
    """Mevcut .env dosyasını key→value dict olarak oku. Çevreleyen tırnakları soyar."""
    sonuc = {}
    if _ENV_PATH.exists():
        for satir in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if satir and not satir.startswith("#") and "=" in satir:
                k, _, v = satir.partition("=")
                sonuc[k.strip()] = v.strip().strip("'\"")
    return sonuc


def _env_yaz(key: str, value: str) -> None:
    set_key(str(_ENV_PATH), key, value)
    os.environ[key] = value


# ─── Token Yönetimi ───────────────────────────────────────────────────────────

def atlassian_refresh(env: dict) -> str:
    """Access token'ı yenile, yeni token döndür ve .env'e kaydet."""
    refresh = env.get("JIRA_REFRESH_TOKEN", "")
    if not refresh:
        raise Exception("Refresh token yok. Jira ile yeniden bağlanın.")
    r = _req.post(
        "https://auth.atlassian.com/oauth/token",
        json={
            "grant_type": "refresh_token",
            "client_id": env.get("JIRA_CLIENT_ID", ""),
            "client_secret": env.get("JIRA_CLIENT_SECRET", ""),
            "refresh_token": refresh,
        },
        timeout=15,
    )
    tokens = r.json()
    if "access_token" not in tokens:
        raise Exception(tokens.get("error_description", "Token yenilenemedi"))
    _env_yaz("JIRA_ACCESS_TOKEN", tokens["access_token"])
    if "refresh_token" in tokens:
        _env_yaz("JIRA_REFRESH_TOKEN", tokens["refresh_token"])
    return tokens["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def atlassian_get(path: str, cloud_id: str, service: str = "jira") -> dict:
    env = env_oku()
    token = env.get("JIRA_ACCESS_TOKEN", "")
    base = f"https://api.atlassian.com/ex/{service}/{cloud_id}"
    r = _req.get(base + path, headers=_auth_headers(token), timeout=30)
    if r.status_code == 401:
        try:
            token = atlassian_refresh(env)
        except Exception as refresh_err:
            raise Exception(f"Yetkilendirme başarısız. Ayarlar → Jira ile yeniden bağlanın. ({refresh_err})")
        r = _req.get(base + path, headers=_auth_headers(token), timeout=30)
    if r.status_code == 401:
        detail = ""
        try:
            detail = r.json().get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        logger.warning("Atlassian 401 [%s] path=%s → %s", service, path, detail)
        if service == "confluence":
            raise Exception(
                "Confluence erişimi reddedildi (401). "
                "Ayarlar → 'Confluence Bağlantısını Test Et' butonuyla hangi izinlerin eksik olduğunu görebilirsiniz. "
                f"Atlassian yanıtı: {detail}"
            )
        raise Exception(f"Atlassian API 401: {detail}")
    r.raise_for_status()
    return r.json()


def atlassian_post(path: str, body: dict, cloud_id: str, service: str = "jira") -> dict:
    env = env_oku()
    token = env.get("JIRA_ACCESS_TOKEN", "")
    base = f"https://api.atlassian.com/ex/{service}/{cloud_id}"
    headers = {**_auth_headers(token), "Content-Type": "application/json"}
    r = _req.post(base + path, json=body, headers=headers, timeout=30)
    if r.status_code == 401:
        token = atlassian_refresh(env)
        headers["Authorization"] = f"Bearer {token}"
        r = _req.post(base + path, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def atlassian_put(path: str, body: dict, cloud_id: str, service: str = "jira") -> dict:
    env = env_oku()
    token = env.get("JIRA_ACCESS_TOKEN", "")
    base = f"https://api.atlassian.com/ex/{service}/{cloud_id}"
    headers = {**_auth_headers(token), "Content-Type": "application/json"}
    r = _req.put(base + path, json=body, headers=headers, timeout=30)
    if r.status_code == 401:
        token = atlassian_refresh(env)
        headers["Authorization"] = f"Bearer {token}"
        r = _req.put(base + path, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    # PUT genellikle 204 No Content döndürür (Jira issue update böyle). Boş body'de
    # r.json() patlar → çağıran taraf "Expecting value" hatası alır ama yazma başarılı.
    if not r.content or r.status_code == 204:
        return {}
    try:
        return r.json()
    except ValueError:
        return {}


# ─── Confluence Sayfa CRUD (v2 API — Modern Mode) ─────────────────────────────

def _confluence_space_id(space_key: str, cloud_id: str) -> str:
    """spaceKey → space_id (v2 API için gerekli)."""
    data = atlassian_get(f"/wiki/api/v2/spaces?keys={space_key}&limit=1", cloud_id, "confluence")
    results = data.get("results", [])
    if not results:
        raise Exception(f"Confluence space bulunamadı: {space_key}")
    return str(results[0]["id"])


def confluence_sayfa_bul(title: str, space_key: str, cloud_id: str) -> dict | None:
    """
    Başlık + space ile sayfa ara (v2 API).
    Bulunursa {"id": ..., "version": n, "url": ...} döndür; yoksa None.
    """
    space_id = _confluence_space_id(space_key, cloud_id)
    encoded = urllib.parse.quote(title)
    data = atlassian_get(
        f"/wiki/api/v2/pages?title={encoded}&space-id={space_id}&limit=1&body-format=storage",
        cloud_id=cloud_id,
        service="confluence",
    )
    results = data.get("results", [])
    if not results:
        return None
    page = results[0]
    return {
        "id": page["id"],
        "version": page.get("version", {}).get("number", 1),
        "url": page.get("_links", {}).get("webui", ""),
    }


def confluence_sayfa_olustur(
    title: str,
    storage_body: str,
    space_key: str,
    cloud_id: str,
    parent_id: str | None = None,
) -> dict:
    """
    Yeni sayfa oluştur (v2 API).
    Döndürür: {"id": ..., "url": ...}
    """
    space_id = _confluence_space_id(space_key, cloud_id)
    payload: dict = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "body": {
            "storage": {
                "value": storage_body,
                "representation": "storage",
            }
        },
    }
    if parent_id:
        payload["parentId"] = parent_id

    data = atlassian_post("/wiki/api/v2/pages", body=payload, cloud_id=cloud_id, service="confluence")
    page_id = data["id"]
    web_url = data.get("_links", {}).get("webui", "")
    base_url = data.get("_links", {}).get("base", "")
    return {"id": page_id, "url": base_url + web_url}


def confluence_sayfa_guncelle(
    page_id: str,
    title: str,
    storage_body: str,
    current_version: int,
    cloud_id: str,
) -> dict:
    """
    Mevcut sayfayı güncelle (v2 API).
    Döndürür: {"id": ..., "url": ...}
    """
    payload = {
        "id": page_id,
        "status": "current",
        "title": title,
        "version": {"number": current_version + 1, "message": ""},
        "body": {
            "storage": {
                "value": storage_body,
                "representation": "storage",
            }
        },
    }
    data = atlassian_put(
        f"/wiki/api/v2/pages/{page_id}",
        body=payload,
        cloud_id=cloud_id,
        service="confluence",
    )
    web_url = data.get("_links", {}).get("webui", "")
    base_url = data.get("_links", {}).get("base", "")
    return {"id": page_id, "url": base_url + web_url}
