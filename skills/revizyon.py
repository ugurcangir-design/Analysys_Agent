"""
Revizyon Oturumu — v2 Faz 1 belkemiği (bkz. docs/ROADMAP-V2.md Faz 1).

Bir analiz çıktısına (ör. `surec-analizi.md`) BAĞLI, durumlu bir revizyon oturumu
tutar. Amaç: tek-atış üretimden, analistle konuşarak ilerleyen, HER değişikliğin
izlendiği ve onaylandığı bir sürece geçiş.

Bu modül DETERMİNİSTİKTİR — hiç AI çağrısı yapmaz, 0 token. Yeni içeriği (tam
yeniden-üretim ya da bölüm-hedefli düzenleme) dışarıdan alır; snapshot'lar,
değişiklik geçmişi, onay/ret ve diff'i yönetir. AI'lı bölüm-hedefli düzenleme
`skills/revizyon_ai.py`/`bolum_duzenle` tarafında; o katman bu modülü çağırır.

Depolama (mevcut analiz akışına DOKUNMAZ — ayrı dizin):
  output/revizyon/<slug>.json          → oturum meta + versiyon listesi + geçmiş
  output/revizyon/<slug>/<vid>.md      → her versiyonun tam içerik snapshot'ı

Kavramlar:
  - versiyon: içeriğin bir anlık tam kopyası (v1, v2, ...). v1 = ilk üretim.
  - aktif_versiyon: `hedef_dosya`'ya yazılı olan, "onaylı" güncel içerik.
  - revizyon (geçmiş kaydı): bir versiyondan diğerine geçiş önerisi. Önerildiğinde
    `beklemede`; analist `onayla()` derse aktif olur ve hedef dosyaya yazılır,
    `reddet()` derse aktif değişmez (öneri versiyonu ölü kalır).
"""

import json
import hashlib
import difflib
from datetime import datetime
from pathlib import Path

from .base import OUTPUT_DIR

REVIZYON_DIR = OUTPUT_DIR / "revizyon"

# Geçerli revizyon tipleri (izleme/etiketleme için)
TIPLER = frozenset({"ilk", "soru-cevap", "sohbet", "bolum", "manuel", "geri-al"})
# Geçerli onay durumları
ONAY_DURUMLARI = frozenset({"beklemede", "onaylandi", "reddedildi"})


# ─── Yardımcılar ──────────────────────────────────────────────────────────────

def _slug(hedef_dosya: str) -> str:
    """`surec-analizi.md` → `surec-analizi`. Yol ayıracı içermez (güvenlik)."""
    ad = Path(hedef_dosya).name
    return ad[:-3] if ad.endswith(".md") else ad


def _simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hash(icerik: str) -> str:
    return hashlib.sha1(icerik.encode("utf-8")).hexdigest()[:12]


def oturum_yolu(hedef_dosya: str) -> Path:
    return REVIZYON_DIR / f"{_slug(hedef_dosya)}.json"


def _versiyon_dir(hedef_dosya: str) -> Path:
    return REVIZYON_DIR / _slug(hedef_dosya)


def _versiyon_yolu(hedef_dosya: str, vid: str) -> Path:
    return _versiyon_dir(hedef_dosya) / f"{vid}.md"


# ─── Depolama ─────────────────────────────────────────────────────────────────

def oturum_var_mi(hedef_dosya: str) -> bool:
    return oturum_yolu(hedef_dosya).exists()


def oturum_yukle(hedef_dosya: str) -> dict | None:
    yol = oturum_yolu(hedef_dosya)
    if not yol.exists():
        return None
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return None


def _oturum_kaydet(oturum: dict) -> None:
    REVIZYON_DIR.mkdir(parents=True, exist_ok=True)
    yol = oturum_yolu(oturum["hedef_dosya"])
    tmp = yol.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(oturum, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(yol)  # POSIX'te atomik


def _versiyon_icerik_yaz(hedef_dosya: str, vid: str, icerik: str) -> None:
    d = _versiyon_dir(hedef_dosya)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{vid}.md").write_text(icerik, encoding="utf-8")


def versiyon_icerik(hedef_dosya: str, vid: str) -> str:
    yol = _versiyon_yolu(hedef_dosya, vid)
    if not yol.exists():
        raise FileNotFoundError(f"Versiyon içeriği yok: {hedef_dosya}/{vid}")
    return yol.read_text(encoding="utf-8")


def _sonraki_id(mevcut: list[dict], on_ek: str) -> str:
    """v1, v2 ... veya r1, r2 ... — mevcut en yüksek numaranın bir fazlası."""
    en_yuksek = 0
    for kayit in mevcut:
        kid = kayit.get("id", "")
        if kid.startswith(on_ek) and kid[len(on_ek):].isdigit():
            en_yuksek = max(en_yuksek, int(kid[len(on_ek):]))
    return f"{on_ek}{en_yuksek + 1}"


# ─── Oturum yaşam döngüsü ─────────────────────────────────────────────────────

def baslat(hedef_dosya: str, icerik: str, not_: str = "İlk üretim") -> dict:
    """Analiz çıktısı için revizyon oturumunu başlatır (v1 = mevcut içerik).

    Oturum zaten varsa dokunmaz ve mevcut oturumu döndürür (idempotent) —
    aynı analiz için çift başlatmada geçmiş kaybolmaz.
    """
    varolan = oturum_yukle(hedef_dosya)
    if varolan is not None:
        return varolan

    v1 = {"id": "v1", "zaman": _simdi(), "hash": _hash(icerik), "not": not_}
    _versiyon_icerik_yaz(hedef_dosya, "v1", icerik)

    oturum = {
        "hedef_dosya": Path(hedef_dosya).name,
        "olusturuldu_at": _simdi(),
        "guncellendi_at": _simdi(),
        "aktif_versiyon": "v1",
        "versiyonlar": [v1],
        "gecmis": [{
            "id": "r1", "zaman": _simdi(), "tip": "ilk",
            "istek": "", "ozet": not_,
            "onceki_versiyon": None, "yeni_versiyon": "v1",
            "degisen_bolumler": [], "onay_durumu": "onaylandi",
        }],
    }
    _oturum_kaydet(oturum)
    return oturum


def revizyon_oner(
    hedef_dosya: str,
    yeni_icerik: str,
    *,
    tip: str = "sohbet",
    istek: str = "",
    ozet: str = "",
    degisen_bolumler: list | None = None,
) -> dict:
    """Yeni bir içerik önerisini oturuma ekler (onay BEKLEMEDE).

    Yeni bir versiyon snapshot'ı yazar ve geçmişe `beklemede` bir kayıt ekler.
    aktif_versiyon DEĞİŞMEZ — analist `onayla()` diyene kadar hedef dosyaya
    yazılmaz. Döner: eklenen geçmiş kaydı (revizyon).
    """
    if tip not in TIPLER:
        raise ValueError(f"Geçersiz tip: {tip}. Kabul edilen: {sorted(TIPLER)}")
    oturum = oturum_yukle(hedef_dosya)
    if oturum is None:
        raise ValueError(f"Oturum yok: {hedef_dosya}. Önce baslat() çağır.")

    onceki = oturum["aktif_versiyon"]
    vid = _sonraki_id(oturum["versiyonlar"], "v")
    _versiyon_icerik_yaz(hedef_dosya, vid, yeni_icerik)
    oturum["versiyonlar"].append({
        "id": vid, "zaman": _simdi(), "hash": _hash(yeni_icerik), "not": ozet or istek,
    })

    rid = _sonraki_id(oturum["gecmis"], "r")
    revizyon = {
        "id": rid, "zaman": _simdi(), "tip": tip,
        "istek": istek, "ozet": ozet,
        "onceki_versiyon": onceki, "yeni_versiyon": vid,
        "degisen_bolumler": degisen_bolumler or [],
        "onay_durumu": "beklemede",
    }
    oturum["gecmis"].append(revizyon)
    oturum["guncellendi_at"] = _simdi()
    _oturum_kaydet(oturum)
    return revizyon


def _revizyon_bul(oturum: dict, revizyon_id: str) -> dict:
    for r in oturum["gecmis"]:
        if r["id"] == revizyon_id:
            return r
    raise ValueError(f"Revizyon bulunamadı: {revizyon_id}")


def onayla(hedef_dosya: str, revizyon_id: str) -> dict:
    """Bekleyen bir revizyonu onaylar → aktif versiyon olur.

    hedef_dosya'nın GERÇEK yazımı çağırana bırakılır: `onayli_icerik()` ile
    yeni içeriği alıp `output/<hedef_dosya>`'ya yazdırır (app.py/skills tarafı,
    IZIN_VERILEN_CIKTILAR kontrolüyle). Döner: güncellenmiş oturum.
    """
    oturum = oturum_yukle(hedef_dosya)
    if oturum is None:
        raise ValueError(f"Oturum yok: {hedef_dosya}")
    r = _revizyon_bul(oturum, revizyon_id)
    if r["onay_durumu"] != "beklemede":
        raise ValueError(f"Revizyon '{revizyon_id}' zaten {r['onay_durumu']}.")
    r["onay_durumu"] = "onaylandi"
    r["onaylandi_at"] = _simdi()
    oturum["aktif_versiyon"] = r["yeni_versiyon"]
    oturum["guncellendi_at"] = _simdi()
    _oturum_kaydet(oturum)
    return oturum


def reddet(hedef_dosya: str, revizyon_id: str) -> dict:
    """Bekleyen bir revizyonu reddeder → aktif versiyon DEĞİŞMEZ.

    Öneri versiyonunun snapshot dosyası tarihsel iz için silinmez; yalnız
    geçmiş kaydı `reddedildi` işaretlenir.
    """
    oturum = oturum_yukle(hedef_dosya)
    if oturum is None:
        raise ValueError(f"Oturum yok: {hedef_dosya}")
    r = _revizyon_bul(oturum, revizyon_id)
    if r["onay_durumu"] != "beklemede":
        raise ValueError(f"Revizyon '{revizyon_id}' zaten {r['onay_durumu']}.")
    r["onay_durumu"] = "reddedildi"
    r["reddedildi_at"] = _simdi()
    oturum["guncellendi_at"] = _simdi()
    _oturum_kaydet(oturum)
    return oturum


def geri_al(hedef_dosya: str, versiyon_id: str, istek: str = "") -> dict:
    """Aktif içeriği daha eski bir versiyona döndürür (yeni onaylı revizyon olarak).

    Geçmişi geriye SİLMEZ; ileriye doğru yeni bir `geri-al` kaydı ekler
    (denetlenebilirlik). Döner: eklenen geçmiş kaydı.
    """
    oturum = oturum_yukle(hedef_dosya)
    if oturum is None:
        raise ValueError(f"Oturum yok: {hedef_dosya}")
    if not any(v["id"] == versiyon_id for v in oturum["versiyonlar"]):
        raise ValueError(f"Versiyon yok: {versiyon_id}")

    onceki = oturum["aktif_versiyon"]
    rid = _sonraki_id(oturum["gecmis"], "r")
    revizyon = {
        "id": rid, "zaman": _simdi(), "tip": "geri-al",
        "istek": istek, "ozet": f"{versiyon_id} sürümüne geri alındı",
        "onceki_versiyon": onceki, "yeni_versiyon": versiyon_id,
        "degisen_bolumler": [], "onay_durumu": "onaylandi", "onaylandi_at": _simdi(),
    }
    oturum["gecmis"].append(revizyon)
    oturum["aktif_versiyon"] = versiyon_id
    oturum["guncellendi_at"] = _simdi()
    _oturum_kaydet(oturum)
    return revizyon


# ─── Okuma / sunum ────────────────────────────────────────────────────────────

def onayli_icerik(hedef_dosya: str) -> str:
    """Aktif (onaylı) versiyonun tam içeriği — hedef dosyaya yazılacak olan."""
    oturum = oturum_yukle(hedef_dosya)
    if oturum is None:
        raise ValueError(f"Oturum yok: {hedef_dosya}")
    return versiyon_icerik(hedef_dosya, oturum["aktif_versiyon"])


def diff(hedef_dosya: str, versiyon_a: str, versiyon_b: str) -> str:
    """İki versiyon arası birleşik (unified) diff — UI'da değişiklik önizleme."""
    a = versiyon_icerik(hedef_dosya, versiyon_a).splitlines(keepends=True)
    b = versiyon_icerik(hedef_dosya, versiyon_b).splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        a, b, fromfile=f"{versiyon_a}", tofile=f"{versiyon_b}", lineterm="",
    ))


def bekleyen_revizyon(hedef_dosya: str) -> dict | None:
    """En son BEKLEMEDE revizyon (varsa) — UI'da onay/ret kartı için."""
    oturum = oturum_yukle(hedef_dosya)
    if oturum is None:
        return None
    for r in reversed(oturum["gecmis"]):
        if r["onay_durumu"] == "beklemede":
            return r
    return None


def ozet(hedef_dosya: str) -> dict | None:
    """UI için oturum özeti: aktif versiyon, versiyon/geçmiş listeleri, bekleyen."""
    oturum = oturum_yukle(hedef_dosya)
    if oturum is None:
        return None
    return {
        "hedef_dosya": oturum["hedef_dosya"],
        "aktif_versiyon": oturum["aktif_versiyon"],
        "versiyon_sayisi": len(oturum["versiyonlar"]),
        "versiyonlar": oturum["versiyonlar"],
        "gecmis": oturum["gecmis"],
        "bekleyen": bekleyen_revizyon(hedef_dosya),
        "guncellendi_at": oturum.get("guncellendi_at"),
    }
