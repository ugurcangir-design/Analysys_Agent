"""Jira Köprüsü — Jira'yı web-chat gibi kullanma (polling + taslak/onay).

Analist, MBSTRADE/MBSOPS gibi bir task'ın YORUMUNA komut yazar:

    /analyst_agent analiz
    /analyst_agent analiz sadece BE tarafını değerlendir
    /analyst_agent yardım

Uygulama (lokal masaüstü, localhost:5003) periyodik bir JQL taramasıyla bu
komutlu yorumları bulur, işler ve sonucu **Jira yorumu** olarak geri yazar.
Inbound bağlantı/webhook/tünel GEREKMEZ — mevcut OAuth + lokal mimariyle uyumlu.

GÜVENLİK İLKELERİ (bkz. CLAUDE.md):
  • Yorum bir KOMUTtur, talimat kaynağı değil (prompt-injection sınırı). Analiz
    girdisi task'ın KENDİ içeriğidir; yorumdaki serbest metin yalnız komut argümanı.
  • Okuma/analiz otomatik (yalnız yorum yazar, Jira ALANLARINA dokunmaz).
    Geri-döndürülemez yazma (task güncelleme / yeni task açma) → TASLAK + ONAY
    (`/analyst_agent onayla`). MVP-2.
  • Varsayılan KAPALI: `JIRA_KOPRU=false`. Owner `.env`'de açar.
  • Kendi yanıtlarımız `ROBOT_IMZA` ile başlar ve komut prefiksiyle BAŞLAMAZ →
    kendi yorumlarımızı asla komut sanmayız (döngü koruması). İşlenen yorum
    id'leri ayrıca durum dosyasında tutulur (tekrar işleme yok).

Bu modül mevcut analiz motoruna (gorev_getir + gorev_analiz_et) sıfır dokunuşla
oturur; Jira'ya yorum yazma canonical atlassian_post üzerindendir.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .atlassian import atlassian_get, atlassian_post
from .jira_gorevleri import (
    _adf_to_text, _cloud_id, _ID_DESENI,
    gorev_getir, gorev_analiz_et,
)
from jira_agent import markdown_to_adf  # ADF: teknik analiz task'ı formatı

BASE_DIR = Path(__file__).resolve().parent.parent
DURUM_DOSYA = BASE_DIR / "output" / "jira-kopru" / "durum.json"

ROBOT_IMZA = "🤖 **Analyst Agent**"      # yanıtlarımızın başı — döngü koruması + tanınırlık
_MAX_ISLENEN = 500                        # durum dosyasında tutulan işlenmiş yorum tavanı


# ─── Ayarlar (.env) ──────────────────────────────────────────────────────────

def _bool(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "evet", "on")


def ayarlar() -> dict:
    """Köprü yapılandırması (.env). Owner makinesinde açılır; varsayılan KAPALI."""
    projeler = [p.strip().upper() for p in os.getenv("JIRA_KOPRU_PROJELER", "").split(",") if p.strip()]
    izinli = [a.strip() for a in os.getenv("JIRA_KOPRU_YAZAR_ALLOWLIST", "").split(",") if a.strip()]
    return {
        "aktif": _bool(os.getenv("JIRA_KOPRU", "false")),
        "aralik_sn": max(20, int(os.getenv("JIRA_KOPRU_ARALIK", "60") or 60)),
        "pencere_dk": max(5, int(os.getenv("JIRA_KOPRU_PENCERE_DK", "120") or 120)),
        "projeler": projeler,
        "komut": os.getenv("JIRA_KOPRU_KOMUT", "/analyst_agent").strip() or "/analyst_agent",
        "yazar_allowlist": izinli,   # displayName veya accountId; boş = herkes
    }


# ─── Durum (işlenen yorumlar — tekrar işleme yok) ────────────────────────────

def _durum_yukle() -> dict:
    try:
        return json.loads(DURUM_DOSYA.read_text(encoding="utf-8"))
    except Exception:
        return {"islenen": {}, "son_tur": None, "son_ozet": None}


def _durum_yaz(d: dict) -> None:
    DURUM_DOSYA.parent.mkdir(parents=True, exist_ok=True)
    # işlenen yorum kaydı sınırsız büyümesin — en yeni _MAX_ISLENEN tut
    islenen = d.get("islenen", {})
    if len(islenen) > _MAX_ISLENEN:
        sirali = sorted(islenen.items(), key=lambda kv: kv[1].get("zaman", ""))
        d["islenen"] = dict(sirali[-_MAX_ISLENEN:])
    DURUM_DOSYA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Jira yorum G/Ç ──────────────────────────────────────────────────────────

def jira_yorum_ekle(key: str, markdown: str) -> bool:
    """Task'a markdown→ADF yorum ekler (canonical atlassian_post). Yalnız YORUM —
    task alanlarına dokunmaz."""
    key = (key or "").strip().upper()
    if not _ID_DESENI.match(key):
        raise ValueError(f"Geçersiz Jira anahtarı: '{key}'")
    icerik = markdown_to_adf(markdown)
    if not icerik:
        raise ValueError("Yorum içeriği boş (ADF üretilemedi).")
    body = {"body": {"type": "doc", "version": 1, "content": icerik}}
    atlassian_post(f"/rest/api/3/issue/{key}/comment", body=body, cloud_id=_cloud_id())
    return True


def _issue_yorumlari(key: str, cloud_id: str) -> list[dict]:
    """Task'ın yorumlarını id + yazar (displayName/accountId) + created + düz metinle
    döndürür (created ARTAN). Komut ayrıştırma ve dedup için id ŞART — bu yüzden
    parse edilmiş görevdeki (id'siz) yorumlar yerine doğrudan comment endpoint'i."""
    yorumlar: list[dict] = []
    baslangic = 0
    while True:
        data = atlassian_get(
            f"/rest/api/3/issue/{key}/comment?orderBy=created&maxResults=100&startAt={baslangic}",
            cloud_id=cloud_id,
        )
        for c in data.get("comments", []) or []:
            yazar = c.get("author") or {}
            govde = c.get("body")
            metin = _adf_to_text(govde) if isinstance(govde, dict) else (govde or "")
            yorumlar.append({
                "id": str(c.get("id", "")),
                "yazar": yazar.get("displayName", ""),
                "hesap": yazar.get("accountId", ""),
                "created": c.get("created", ""),
                "metin": (metin or "").strip(),
            })
        toplam = data.get("total", len(yorumlar))
        baslangic += data.get("maxResults", 100)
        if baslangic >= toplam or not data.get("comments"):
            break
    return yorumlar


# ─── Komut ayrıştırma ────────────────────────────────────────────────────────

def _komut_coz(metin: str, prefix: str) -> tuple[str, str] | None:
    """Yorum metni komut prefiksiyle başlıyorsa (komut, argüman) döndürür; değilse None.
    Örn. '/analyst_agent analiz sadece BE' → ('analiz', 'sadece BE')."""
    s = (metin or "").strip()
    if not s.lower().startswith(prefix.lower()):
        return None
    kalan = s[len(prefix):].strip()
    if not kalan:
        return ("yardim", "")
    parca = kalan.split(None, 1)
    komut = parca[0].strip().lower().lstrip("/")
    arg = parca[1].strip() if len(parca) > 1 else ""
    # Türkçe/aksan eşanlamlıları tek anahtara indir
    esanlam = {
        "yardım": "yardim", "help": "yardim", "?": "yardim",
        "analyze": "analiz", "analiz-et": "analiz",
        "ilişkili-aç": "iliskili-ac", "iliskili-ac": "iliskili-ac", "ilişkiliaç": "iliskili-ac",
        "güncelle": "guncelle",
        "onayla": "onayla", "approve": "onayla",
    }
    return (esanlam.get(komut, komut), arg)


def _yazar_izinli(yorum: dict, izinliler: list[str]) -> bool:
    if not izinliler:
        return True
    return yorum.get("yazar", "") in izinliler or yorum.get("hesap", "") in izinliler


def _yardim_metni(prefix: str) -> str:
    return (
        f"{ROBOT_IMZA} — komutlar\n\n"
        f"- `{prefix} analiz` — bu task'ı teknik analiz eder, sonucu yorum olarak yazar (okuma; alanlara dokunmaz).\n"
        f"- `{prefix} analiz <talimat>` — talimatlı analiz (örn. *sadece BE tarafını değerlendir*).\n"
        f"- `{prefix} güncelle` — analizi task açıklamasına yazmayı önerir → **onay** gerekir. _(yakında)_\n"
        f"- `{prefix} ilişkili-aç` — analizden ilişkili task önerir → **onay** gerekir. _(yakında)_\n"
        f"- `{prefix} yardım` — bu liste.\n\n"
        f"_Güvenlik: yorum bir komuttur; task'ı değiştiren işlemler yalnız açık onaydan sonra yapılır._"
    )


# ─── Komut işleme ────────────────────────────────────────────────────────────

def _analiz_islet(key: str, arg: str) -> str:
    """`analiz` komutu — task'ı analiz eder, yorum metni (markdown) döndürür.
    Jira ALANLARINA yazmaz; yalnız analiz sonucunu yorum olarak sunar."""
    gorev = gorev_getir(key)
    if not gorev:
        return f"{ROBOT_IMZA}\n\n⚠ `{key}` okunamadı (yetki/erişim?). Analiz yapılamadı."
    sonuc = gorev_analiz_et(gorev, cevaplar=arg or "")
    md = (sonuc.get("markdown") or "").strip()
    acik = (sonuc.get("acik_sorular") or "").strip()
    prefix = ayarlar()["komut"]
    parcalar = [f"{ROBOT_IMZA} — Teknik Analiz · `{key}`", "", md]
    if acik and acik.lower() not in ("açık soru tespit edilmedi.", "acik soru tespit edilmedi."):
        parcalar += ["", "---", "**Açık Sorular**", "", acik]
    parcalar += [
        "", "---",
        f"_Bu bir taslak analizdir; Jira alanları **değiştirilmedi**. "
        f"Açıklamaya yazmak için `{prefix} güncelle`, ilişkili task önerileri için "
        f"`{prefix} ilişkili-aç` (onay gerekir)._",
    ]
    return "\n".join(parcalar)


def _komut_uygula(komut: str, arg: str, key: str, prefix: str) -> str:
    """Komutu işleyip Jira'ya yazılacak YANIT markdown'ını döndürür."""
    if komut == "yardim":
        return _yardim_metni(prefix)
    if komut == "analiz":
        return _analiz_islet(key, arg)
    if komut in ("guncelle", "iliskili-ac", "onayla"):
        return (
            f"{ROBOT_IMZA}\n\n`{komut}` komutu **taslak + onay** akışıyla yakında gelecek (MVP-2). "
            f"Şimdilik `{prefix} analiz` ile analiz alabilirsiniz."
        )
    return (
        f"{ROBOT_IMZA}\n\n❓ Bilinmeyen komut: `{komut}`. `{prefix} yardım` ile komut listesine bakın."
    )


# ─── Tek tur (elle /tara ve arka plan döngüsü ortak yolu) ────────────────────

def tek_tur(pencere_dk: int | None = None) -> dict:
    """Komutlu yeni yorumları bir kez tarar ve işler. Döner:
        {"ok", "taranan_task", "islenen":[{key,komut,yazar}], "atlanan", "hata":[...]}.
    Elle `/api/jira-kopru/tara` ve arka plan döngüsü aynı yolu kullanır."""
    ayar = ayarlar()
    if not ayar["projeler"]:
        return {"ok": False, "error": "JIRA_KOPRU_PROJELER tanımlı değil (.env)."}
    cloud_id = _cloud_id()   # Jira bağlı değilse net RuntimeError
    pencere = pencere_dk or ayar["pencere_dk"]
    prefix = ayar["komut"]
    durum = _durum_yukle()
    islenen_kayit = durum.setdefault("islenen", {})

    projeler = ",".join(ayar["projeler"])
    jql = f"project in ({projeler}) AND updated >= \"-{pencere}m\" ORDER BY updated DESC"
    body = {"jql": jql, "fields": ["summary"], "maxResults": 100}
    data = atlassian_post("/rest/api/3/search/jql", body=body, cloud_id=cloud_id)
    task_keys = [i.get("key") for i in data.get("issues", []) if i.get("key")]

    islenen: list[dict] = []
    hatalar: list[dict] = []
    atlanan = 0
    for key in task_keys:
        try:
            yorumlar = _issue_yorumlari(key, cloud_id)
        except Exception as e:
            hatalar.append({"key": key, "hata": f"yorum okunamadı: {e}"})
            continue
        for y in yorumlar:
            cid = y["id"]
            if not cid or cid in islenen_kayit:
                continue
            coz = _komut_coz(y["metin"], prefix)
            if not coz:
                continue  # komut değil (kendi 🤖 yanıtlarımız da buraya düşer)
            komut, arg = coz
            if not _yazar_izinli(y, ayar["yazar_allowlist"]):
                # İşlendi say (tekrar denenmesin) ama reddi bildir.
                islenen_kayit[cid] = {"key": key, "komut": komut, "zaman": _simdi(), "red": "yazar-izinsiz"}
                atlanan += 1
                try:
                    jira_yorum_ekle(key, f"{ROBOT_IMZA}\n\n⛔ `{y['yazar']}` bu komutu çalıştırma yetkisinde değil.")
                except Exception:
                    pass
                continue
            try:
                yanit = _komut_uygula(komut, arg, key, prefix)
                jira_yorum_ekle(key, yanit)
                islenen_kayit[cid] = {"key": key, "komut": komut, "yazar": y["yazar"], "zaman": _simdi()}
                islenen.append({"key": key, "komut": komut, "yazar": y["yazar"]})
            except Exception as e:
                hatalar.append({"key": key, "komut": komut, "hata": str(e)})
                # Hatada da işlendi işaretle (aynı hatayı token yakarak tekrarlama);
                # kullanıcıya kısa hata yorumu bırak.
                islenen_kayit[cid] = {"key": key, "komut": komut, "zaman": _simdi(), "hata": str(e)}
                try:
                    jira_yorum_ekle(key, f"{ROBOT_IMZA}\n\n⚠ Komut işlenemedi: {e}")
                except Exception:
                    pass

    ozet = {"ok": True, "taranan_task": len(task_keys), "islenen": islenen,
            "atlanan": atlanan, "hata": hatalar, "zaman": _simdi()}
    durum["son_tur"] = ozet["zaman"]
    durum["son_ozet"] = {"taranan_task": len(task_keys), "islenen": len(islenen),
                         "atlanan": atlanan, "hata": len(hatalar)}
    _durum_yaz(durum)
    return ozet


def son_durum() -> dict:
    """UI/endpoint için köprü durumu (0 token)."""
    d = _durum_yukle()
    return {"ayarlar": {k: v for k, v in ayarlar().items()},
            "son_tur": d.get("son_tur"), "son_ozet": d.get("son_ozet"),
            "islenen_toplam": len(d.get("islenen", {}))}


def _simdi() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
