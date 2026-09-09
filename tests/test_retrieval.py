"""
BM25 referans retrieval — deterministik test (v2 Faz 3 · 3.c-i). AI/kota/dep YOK.
Çalıştır:  venv/bin/python tests/test_retrieval.py
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import skills.retrieval as rt   # noqa: E402

ok = 0


def dogru(kosul, ad):
    global ok
    assert kosul, f"FAIL {ad}"
    ok += 1
    print(f"  ✓ {ad}")


# Parçalama
metin = ("\n\n".join(f"Paragraf {i} içerik metni burada." for i in range(20)))
p = rt.parcala(metin, boyut=200, ortusme=40)
dogru(len(p) >= 3, "parçalama birden çok parça üretir")
dogru(all(x["metin"].strip() for x in p), "boş parça yok")

# BM25 sıralama: iade/refund geçen parça en üste (gerçekçi büyüklükte bölümler)
def bolum(baslik, govde):
    return baslik + "\n" + (govde + " ") * 60 + "\n\n"

belge = (
    bolum("Kullanıcı profili", "Ad soyad e-posta dil seçimi tercihler ekranı düzenleme.")
    + bolum("Cüzdan iade akışı", "iade talebi oluşturulur refund tutarı hesaplanır onaya düşer para geri.")
    + bolum("Raporlama modülü", "aylık gelir grafikleri dışa aktarma pano özet tablo.")
    + bolum("Bildirim ayarları", "e-posta anlık bildirim tercih sıklık kanal.")
)
r = rt.en_alakali_parcalar(belge, "iade refund onay para", k=2, butce=8000)
dogru(r["ok"] and r["secilen"], "BM25 seçim yaptı")
dogru(r["parca_sayisi"] >= 3, "belge birden çok parçaya bölündü")
dogru("iade" in r["secilen"][0]["metin"] and "refund" in r["secilen"][0]["metin"], "en yüksek skorlu parça = iade")
dogru("Raporlama" not in r["secilen"][0]["metin"], "alakasız parça ilk sırada değil")

# Alaka yoksa baştan kesim (fallback)
r2 = rt.en_alakali_parcalar(belge, "kuantum fiziği xyzzy", k=2, butce=80)
dogru(r2["ok"] and len(r2["metin"]) <= 80, "alaka yok → baştan kesim bütçesi")

# Boş / sorgu-yok
dogru(rt.en_alakali_parcalar("", "x")["parca_sayisi"] == 0, "boş metin")
dogru(rt.en_alakali_parcalar(belge, "")["metin"], "boş sorgu → baştan döndürür")

# Türkçe casefold: İ/ı
toks = rt._tokenle("İADE İşlemi ıslak")
dogru("iade" in toks and "işlemi" in toks, "Türkçe casefold tokenizasyon")

print(f"\nRETRIEVAL TESTLERİ GEÇTİ ({ok} kontrol)")
