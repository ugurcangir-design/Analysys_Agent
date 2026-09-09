"""
Bölüm-hedefli AI düzenleme — v2 Faz 1 · Artım 2 (bkz. docs/ROADMAP-V2.md).

Analistin "şu bölümü şöyle değiştir" isteğini, TÜM dokümanı yeniden üretmeden
karşılar: yalnız hedef bölümü AI'a gönderir, dönen düzenlenmiş bölümü dokümana
geri yerleştirir (splice) ve sonucu `revizyon.revizyon_oner()` ile ONAY BEKLEYEN
bir öneri olarak kaydeder. Böylece:
  - tek-atış tam yeniden-üretim yok → daha ucuz, daha isabetli, format korunur
  - her düzenleme revizyon geçmişine düşer, analist onaylar/reddeder (belkemiği: revizyon.py)

Bölüm ayırma/splice DETERMİNİSTİKTİR (0 token, test edilir). Yalnız `bolum_duzenle`
içindeki tek AI çağrısı token harcar; test/enjeksiyon için `_ai_fn` parametresiyle
soyutlandı.
"""

import re
from pathlib import Path

from . import revizyon
from .base import _api_cagri, OUTPUT_DIR, MAX_TOKENS_KISA

# Markdown başlık satırı: "## Başlık", "### PA-001: ...", vb.
_BASLIK = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*$", re.MULTILINE)

# Bölüm-hedefli düzenleme sistem promptu. TÜM doküman değil, YALNIZ hedef bölüm
# gönderilir; AI aynı başlığı koruyarak yalnız bu bölümü döndürür.
# Not: Faz 2'de UI'dan düzenlenebilir olması için base.VARSAYILAN_PROMPTLAR'a
# taşınabilir; şu an v2-yeni yetenek olduğundan modülde tutuluyor (base.py'ye
# dokunmadan, düşük risk).
REFINE_BOLUM_PROMPT = """# ROL
Bir analiz dokümanının TEK bir bölümünü, analistin talimatına göre cerrahi
hassasiyetle düzenleyen kıdemli analistsin.

# GÖREV
Sana dokümanın YALNIZCA bir bölümü verildi. Analistin talimatını bu bölüme uygula.

# KESİN KURALLAR
- Yalnız verilen bölümü döndür — başka bölüm, giriş/kapanış cümlesi, açıklama EKLEME.
- Bölümün başlık satırını (örn. "## ...", "### PA-001: ...") AYNEN koru.
- Talimatın dokunmadığı satırları KELİMESİ KELİMESİNE koru.
- ID'leri (PA/BR/AC/EK/T-/Q- vb.), tablo yapısını ve Markdown formatını bozma.
- Talimat belirsizse mevcut içeriği bozmadan en yakın makul yorumu uygula.

# ANALİST TALİMATI
{talimat}

# DÜZENLENECEK BÖLÜM
{bolum}

# ÇIKTI
Yalnızca düzenlenmiş bölümün Markdown'ını ver (başlık dahil). Başka hiçbir şey yazma."""


def bolumlere_ayir(md: str) -> list[dict]:
    """Markdown'ı başlıklara göre iç içe olmayan bölümlere ayırır.

    Her bölüm bir başlıkla başlar ve seviyesi <= kendi seviyesi olan bir SONRAKİ
    başlığa kadar sürer (alt başlıklar bölüme dahildir). Başlık öncesi önsöz
    varsa `seviye=0`, `baslik=""` bir giriş bloğu olarak döner.

    Döner: [{indeks, seviye, baslik, baslangic, bitis, icerik}] — `baslangic`/`bitis`
    `md` içinde karakter ofsetleridir (splice için).
    """
    basliklar = [
        {"seviye": len(m.group(1)), "baslik": m.group(2).strip(), "satir_bas": m.start()}
        for m in _BASLIK.finditer(md)
    ]
    bolumler: list[dict] = []

    # Başlıktan önce önsöz (ör. HTML meta yorumu, yönetici özeti) varsa koru
    ilk = basliklar[0]["satir_bas"] if basliklar else len(md)
    if ilk > 0:
        bolumler.append({
            "indeks": 0, "seviye": 0, "baslik": "",
            "baslangic": 0, "bitis": ilk, "icerik": md[:ilk],
        })

    for i, b in enumerate(basliklar):
        bas = b["satir_bas"]
        bitis = len(md)
        for sonraki in basliklar[i + 1:]:
            if sonraki["seviye"] <= b["seviye"]:
                bitis = sonraki["satir_bas"]
                break
        bolumler.append({
            "indeks": len(bolumler), "seviye": b["seviye"], "baslik": b["baslik"],
            "baslangic": bas, "bitis": bitis, "icerik": md[bas:bitis],
        })
    return bolumler


def bolum_bul(md: str, anahtar: str) -> dict | None:
    """Başlığı `anahtar`'ı içeren İLK bölüm (küçük/büyük harf duyarsız).

    `anahtar` bir ID (PA-001), başlık metni veya parçası olabilir. En düşük
    seviyeli (en spesifik) eşleşme değil, dokümandaki ilk eşleşme döner —
    çağıran taraf tam başlık verirse tekil olur.
    """
    hedef = anahtar.strip().casefold()
    if not hedef:
        return None
    for b in bolumlere_ayir(md):
        if b["seviye"] == 0:
            continue
        if hedef in b["baslik"].casefold():
            return b
    return None


def _refine_bolum_ai(talimat: str, bolum: str) -> str:
    """Tek AI çağrısı — yalnız hedef bölümü düzenler. Token harcayan tek nokta."""
    sistem = REFINE_BOLUM_PROMPT.format(talimat=talimat, bolum=bolum)
    mesajlar = [{"role": "user", "content": [
        {"type": "text", "text": "Talimatı bu bölüme uygula ve yalnız bölümü döndür."}
    ]}]
    # Analistin açık düzenleme isteği — önbellekten değil, taze üret.
    return _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_KISA, onbellek=False)


def bolum_duzenle(
    hedef_dosya: str,
    anahtar: str,
    talimat: str,
    *,
    _ai_fn=_refine_bolum_ai,
) -> dict:
    """Hedef bölümü AI ile düzenler ve ONAY BEKLEYEN bir revizyon önerisi oluşturur.

    Akış:
      1. Aktif (onaylı) içeriği revizyon oturumundan al (oturum yoksa dosyadan başlat).
      2. `anahtar`'a uyan bölümü bul; yoksa ValueError.
      3. Yalnız o bölümü AI'a gönder (`_ai_fn`), düzenlenmiş bölümü al.
      4. Bölümü dokümana geri yerleştir (splice) → yeni tam içerik.
      5. `revizyon.revizyon_oner(... tip='bolum' ...)` ile beklemede öneri kaydet.

    Döner: eklenen revizyon (beklemede). Analist app.py'den onayla/reddet eder.
    `_ai_fn` yalnız test/enjeksiyon içindir (imza: (talimat, bolum) -> str).
    """
    talimat = (talimat or "").strip()
    if not talimat:
        raise ValueError("Düzenleme talimatı boş.")

    # 1) Aktif içerik — oturum varsa ondan, yoksa dosyadan başlat
    if revizyon.oturum_var_mi(hedef_dosya):
        mevcut = revizyon.onayli_icerik(hedef_dosya)
    else:
        yol = OUTPUT_DIR / Path(hedef_dosya).name
        if not yol.exists():
            raise FileNotFoundError(f"Çıktı yok: {hedef_dosya}")
        mevcut = yol.read_text(encoding="utf-8")
        revizyon.baslat(hedef_dosya, mevcut, not_="İlk üretim (revizyon oturumu açıldı)")

    # 2) Hedef bölüm
    bolum = bolum_bul(mevcut, anahtar)
    if bolum is None:
        raise ValueError(f"Bölüm bulunamadı: '{anahtar}'")

    # 3) AI düzenleme (yalnız bölüm)
    yeni_bolum = _ai_fn(talimat, bolum["icerik"]).strip("\n")
    # Bölümler arası tek boş satır düzenini koru (splice sonrası ardışık \n\n)
    if not yeni_bolum.endswith("\n"):
        yeni_bolum += "\n"
    # Orijinal bölüm sonundaki boşluk düzenini yaklaşık koru
    kuyruk = "\n" if bolum["icerik"].endswith("\n\n") else ""

    # 4) Splice
    yeni_icerik = mevcut[:bolum["baslangic"]] + yeni_bolum + kuyruk + mevcut[bolum["bitis"]:]

    # 5) Beklemede öneri
    return revizyon.revizyon_oner(
        hedef_dosya, yeni_icerik,
        tip="bolum",
        istek=talimat,
        ozet=f"'{bolum['baslik']}' bölümü düzenlendi",
        degisen_bolumler=[{
            "section": bolum["baslik"], "changeType": "updated",
            "reason": talimat[:160],
        }],
    )
