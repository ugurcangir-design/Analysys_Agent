"""
Referans Retrieval — v2 Faz 3 · Artım 3.c-i (bkz. docs/ROADMAP-V2.md Faz 3).

Büyük referans dokümanlardan analize İLGİLİ bölümleri getirme. Mevcut keyword-window
çıkarımına (base._keyword_odakli_metin) göre daha isabetli: dokümanı parçalara böler,
sorguya karşı **BM25** ile sıralar, en alakalı parçaları bütçe içinde döndürür.

Saf Python — YENİ DEPENDENCY YOK, 0 token, deterministik. Embedding-tabanlı gerçek
semantik retrieval, aynı `en_alakali_parcalar` arayüzünü uygulayan bir backend olarak
sonradan takılabilir (kod_kaynagi gibi "hazır arayüz" felsefesi).
"""

import math
import re

# Türkçe + genel: harf/rakam dizileri; casefold Türkçe İ/ı'yı doğru indirger.
_TOKEN = re.compile(r"[0-9a-zçğıöşü_]+", re.IGNORECASE)
# Aramada gürültü yapan çok yaygın kelimeler (idf zaten bastırır; yine de eleriz).
_STOP = frozenset("""
ve veya ile ama fakat için gibi daha çok az bir bu şu o da de ki mi mı mu mü
the a an of to in on for and or is are be with as by at from that this
""".split())

MIN_TOKEN = 2


def _tokenle(metin: str) -> list[str]:
    # casefold + Türkçe İ→"i̇" birleşik noktasını (U+0307) at → "İADE" ve "iade" eşleşir.
    metin = metin.casefold().replace("̇", "")
    return [t for t in (m.group(0) for m in _TOKEN.finditer(metin))
            if len(t) >= MIN_TOKEN and t not in _STOP]


def parcala(metin: str, boyut: int = 1200, ortusme: int = 200) -> list[dict]:
    """Metni, paragraf sınırlarına saygılı, örtüşen parçalara böler.
    Dönen: [{indeks, baslangic, bitis, metin}]."""
    if not metin:
        return []
    # Paragrafları koru; parça sınırını mümkünse paragraf/satır sonuna çek.
    parcalar: list[dict] = []
    n = len(metin)
    i = 0
    while i < n:
        j = min(i + boyut, n)
        if j < n:
            # en yakın paragraf/satır sonuna kadar uzat (küçük bir tolerans)
            kesme = metin.rfind("\n\n", i, j)
            if kesme == -1 or kesme <= i + boyut // 2:
                kesme = metin.rfind("\n", i, j)
            if kesme > i + boyut // 2:
                j = kesme
        parca = metin[i:j]
        if parca.strip():
            parcalar.append({"indeks": len(parcalar), "baslangic": i, "bitis": j, "metin": parca})
        if j >= n:
            break
        i = max(j - ortusme, i + 1)
    return parcalar


class BM25:
    """Klasik BM25 (Okapi). Küçük doküman setleri için yeterli, bağımlılıksız."""

    def __init__(self, dokumanlar: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.dokumanlar = dokumanlar
        self.N = len(dokumanlar) or 1
        self.uzunluk = [len(d) for d in dokumanlar]
        self.ort_uzunluk = (sum(self.uzunluk) / self.N) if self.N else 0.0
        # döküman frekansı
        df: dict[str, int] = {}
        self.tf: list[dict[str, int]] = []
        for d in dokumanlar:
            sayac: dict[str, int] = {}
            for t in d:
                sayac[t] = sayac.get(t, 0) + 1
            self.tf.append(sayac)
            for t in sayac:
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def skor(self, sorgu: list[str], i: int) -> float:
        if not self.ort_uzunluk:
            return 0.0
        tf, ul = self.tf[i], self.uzunluk[i]
        s = 0.0
        for t in sorgu:
            f = tf.get(t)
            if not f:
                continue
            idf = self.idf.get(t, 0.0)
            s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * ul / self.ort_uzunluk))
        return s

    def sirala(self, sorgu: list[str]) -> list[tuple[int, float]]:
        skorlar = [(i, self.skor(sorgu, i)) for i in range(self.N)]
        skorlar.sort(key=lambda x: -x[1])
        return skorlar


def en_alakali_parcalar(metin: str, sorgu: str, k: int = 6, butce: int = 12000) -> dict:
    """`metin`i parçalayıp `sorgu`ya en alakalı parçaları BM25 ile döndürür.

    Dönen: {ok, parca_sayisi, secilen:[{indeks,skor,metin}], metin: birleşik-bütçeli}.
    Alaka sinyali yoksa (tüm skorlar 0) belge başından bütçe kadar düşer (fallback).
    """
    parcalar = parcala(metin)
    if not parcalar:
        return {"ok": True, "parca_sayisi": 0, "secilen": [], "metin": ""}
    sorgu_tok = _tokenle(sorgu)
    if not sorgu_tok:
        kes = metin[:butce]
        return {"ok": True, "parca_sayisi": len(parcalar), "secilen": [], "metin": kes}

    bm = BM25([_tokenle(p["metin"]) for p in parcalar])
    sirali = bm.sirala(sorgu_tok)
    if not sirali or sirali[0][1] <= 0:
        kes = metin[:butce]
        return {"ok": True, "parca_sayisi": len(parcalar), "secilen": [], "metin": kes,
                "not": "alaka bulunamadı — baştan kesim"}

    secilen = []
    toplam = 0
    for i, skor in sirali[:max(1, k)]:
        if skor <= 0 or toplam >= butce:
            break
        p = parcalar[i]
        secilen.append({"indeks": i, "skor": round(skor, 3), "metin": p["metin"]})
        toplam += len(p["metin"])
    # Belge sırasına göre diz (okunabilirlik), aralara ayraç
    secilen_sirali = sorted(secilen, key=lambda x: x["indeks"])
    birlesik = "\n\n[…]\n\n".join(s["metin"] for s in secilen_sirali)
    return {"ok": True, "parca_sayisi": len(parcalar), "secilen": secilen, "metin": birlesik[:butce]}
