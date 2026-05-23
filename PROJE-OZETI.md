# Analyst Studio — Proje Özeti

> AI destekli iş analizi otomasyon aracı. İş gereksinim dokümanlarını
> (BRD / süreç tarifi) yapılandırılmış analiz raporlarına, prototiplere ve
> Jira görev hiyerarşilerine dönüştürür.

---

## 1. Proje Nedir?

**Analyst Studio**, bir iş/sistem analistinin manuel olarak günler süren
çalışmasını dakikalara indiren bir masaüstü uygulamasıdır. Kullanıcı bir
gereksinim dokümanı yükler; uygulama bu dokümanı kurumsal bilgi kaynaklarıyla
(Confluence, Jira, API tanımları, mevcut kod) zenginleştirerek geliştirme
ekibinin doğrudan kullanabileceği analiz çıktıları üretir.

**Kullanıcı kitlesi:** İş analistleri, sistem analistleri, ürün sahipleri,
yazılım mimarları.

**Temel değer önerisi:** Gereksinim → analiz → planlanmış geliştirme görevi
zincirini, kurumsal bağlamı kaybetmeden ve insan denetimini koruyarak
otomatikleştirmek.

---

## 2. Çözdüğü Problem

Klasik iş analizi sürecinde:
- Analist BRD'yi okur, eksikleri/çelişkileri elle tespit eder
- Mevcut sistem dokümantasyonunu (Confluence, API, kod) tek tek tarar
- Süreç ve teknik analiz dokümanlarını sıfırdan yazar
- Geliştirme görevlerini elle Jira'ya girer

Bu süreç **yavaş**, **tutarsız** (her analist farklı yazar) ve **bağlamı
kaçırmaya açıktır** (mevcut endpoint'ler, tablolar gözden kaçar).

Analyst Studio bu zinciri, **kanıt temelli (RAG)** bir AI mimarisiyle
otomatikleştirir; her adımda insan onayı alarak kontrolü kullanıcıda tutar.

---

## 3. Nasıl Çalışır? — Mimari

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Tarayıcı SPA   │────▶│  Flask Sunucusu  │────▶│  Claude API     │
│  (tek sayfa UI) │◀────│  (app.py, 5002)  │◀────│  (Anthropic)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
              ┌─────────┐ ┌─────────┐ ┌──────────┐
              │ skills/ │ │workflow │ │ Atlassian│
              │ modüller│ │ durum   │ │ (Jira /  │
              │         │ │ makinesi│ │Confluence)│
              └─────────┘ └─────────┘ └──────────┘
```

- **Çalışma biçimi:** macOS masaüstü uygulaması (`Analyst Studio.app`).
  Çift tıklanır, arka planda yerel bir Flask sunucusu başlar, tarayıcıda
  tek sayfalık arayüz açılır.
- **Dil/teknoloji:** Python 3.12, Flask; arayüz tek dosya HTML/CSS/JS (SPA).
- **AI motoru:** Anthropic Claude API.
- **Mimari desen:** Web isteği → Flask → `subprocess` ile orkestratör →
  `skills/` modülleri → Claude API. Arayüz 1.5 sn aralıkla durum sorgular.
- **Durum yönetimi:** `workflow.py` içinde bir durum makinesi her analizin
  hangi aşamada olduğunu izler ve geçersiz geçişleri engeller.

---

## 4. İş Akışı (İki Pipeline)

Uygulama iki ana akış sunar; her adım bir önceki adımın çıktısını girdi alır
ve **her kritik adımda kullanıcı onayı** beklenir.

### A) Süreç → Teknik → Jira akışı (ana akış)
```
Süreç dokümanı yüklenir
   │
   ▼
1. SÜREÇ ANALİZİ  ──▶ surec-analizi.md
   │  (kullanıcı onayı)
   ▼
2. TEKNİK ANALİZ  ──▶ teknik-analiz.md + acik-sorular.md
   │  (kullanıcı onayı)
   ▼
3. HTML PROTOTİP (opsiyonel) ──▶ mockup.html
   │
   ▼
4. JİRA GÖREV HİYERARŞİSİ
   - AI önizleme üretir (Epic / Story / Subtask)
   - Kullanıcı ekrandan seçim yapar (FE / BE rozetleriyle)
   - Seçilenler Jira'da açılır
```

### B) BRD → Kapsam akışı
```
BRD dokümanı yüklenir
   │
   ▼
1. BRD ANALİZİ  ──▶ brd-analizi.md + brd-sorular.md (PO soruları)
   │
   ▼
2. KAPSAM ANALİZİ (revize BRD ile karşılaştırma)
        ──▶ kapsam-analizi.md + alternatif-surecler.md
```

Üretilen analizler ayrıca **Confluence'a sayfa olarak yayımlanabilir**.

---

## 5. AI / RAG Mimarisi

Bu projenin çekirdeği **RAG (Retrieval-Augmented Generation)** yaklaşımıdır:
AI hiçbir bilgiyi "uydurmaz", her çıktıyı sağlanan kaynaklara dayandırır.

### Bağlam kaynakları (otomatik dahil edilir)
| Kaynak | İçerik | Kullanım |
|--------|--------|----------|
| **Confluence** | Mimari kararlar, DB şeması, sistem dokümantasyonu | Mevcut yapıyı anlamak |
| **Jira** | Geçmiş görevler, kararlar | Tekrar/çelişki tespiti |
| **Swagger/OpenAPI** | Mevcut servis endpoint'leri, şemalar | Gerçek API'leri kullanmak |
| **UI kodu** | Mevcut frontend kaynak kodu | Mevcut ekranları tanımak |
| **Mevcut BRD** | Aktif gereksinim dokümanı | Kapsam karşılaştırması |

### RAG kalite mekanizmaları (prompt seviyesinde)
- **Kanıt temelli üretim:** Her somut iddia `[K: kaynak]` etiketiyle
  işaretlenir; kaynaksız iddia ana metne giremez, "Açık Sorular"a taşınır.
- **Halüsinasyon koruması (Entity Whitelist):** Endpoint, tablo, rol adı
  gibi varlıklar yalnızca referanslarda gerçekten geçiyorsa kullanılır.
- **Çakışma yönetimi:** İki kaynak çelişirse öncelik sırası uygulanır
  (Swagger > Confluence > BRD > Jira > UI kodu) ve çelişki raporlanır.
- **İzlenebilirlik:** Her aşama numaralı ID üretir (BRD: FR/NFR, süreç:
  PA/BR/EK, teknik: T-FE/T-BE); ID'ler aşamalar arası takip edilir.
- **Bağlam filtresi:** Kullanıcı anahtar kelime/Jira anahtarı belirterek
  yalnızca ilgili kaynakların dahil edilmesini sağlayabilir.

### Kullanılan modeller
- **claude-sonnet-4-6** — tüm analiz üretimi (süreç, teknik, BRD, kapsam)
- **claude-haiku-4-5** — Jira görev başlığı üretimi (hafif iş)

### Maliyet/performans optimizasyonu
- **Prompt caching:** Referans kaynaklar ve sistem promptu önbelleğe alınır;
  tekrar çalıştırmalarda ~%90 token tasarrufu.
- **Combined XML pattern:** Tek API çağrısında iki çıktı üretilir
  (örn. teknik analiz + açık sorular birlikte).
- **Exponential backoff retry:** API hatalarında (429/5xx) otomatik tekrar.

### Prompt mühendisliği
15 ayrı sistem promptu, tutarlı bir yapıda kurgulanmıştır:
`ROL → GÖREV → ÇIKTININ AMACI → ÇALIŞMA YÖNTEMİ → RAG İLKESİ → BAĞLAM
KULLANIMI → KALİTE ÖLÇÜTÜ`. Promptlar uygulama arayüzünden düzenlenebilir.

### FE / BE katman ayrımı
Analiz, işi **Frontend (FE)** ve **Backend (BE)** olarak sınıflandırır;
böylece teknik analizden ayrı ama ilişkili FE/BE geliştirme görevleri üretilir
ve Jira'da bu ayrımla açılır.

---

## 6. Üretilen Çıktılar

| Çıktı | Açıklama |
|-------|----------|
| `surec-analizi.md` | Aktörler, süreç adımları, iş kuralları, veri varlıkları, ekranlar (FE), kabul kriterleri, açık sorular — teknik analize hazır kaynak |
| `teknik-analiz.md` | Mimari, DDL, OpenAPI YAML, validasyon matrisi, güvenlik, test stratejisi, FE teknik tasarımı, FE/BE iş kırılımı |
| `acik-sorular.md` | Teknik analizde netleşmesi gereken sorular |
| `brd-analizi.md` | Fonksiyonel/fonksiyonel olmayan gereksinimler, paydaşlar, eksiklik/tutarsızlık tespiti |
| `brd-sorular.md` | Product Owner'a yöneltilecek netleştirme soruları |
| `kapsam-analizi.md` | İki BRD versiyonu arası fark analizi (eklenen/çıkarılan/değişen) |
| `alternatif-surecler.md` | Revize kapsamı karşılayan 3-5 uygulama alternatifi |
| `mockup.html` | Çalışan, tıklanabilir HTML arayüz prototipi |
| **Jira görevleri** | Epic + Story + Subtask hiyerarşisi (FE/BE etiketli, seçmeli) |
| **Confluence sayfası** | Analiz dokümanlarının kurumsal wiki'ye yayımlanmış hali |

---

## 7. Entegrasyonlar

- **Atlassian Jira** — OAuth 3LO ile bağlantı; görev oluşturma/güncelleme,
  Epic/Story/Subtask hiyerarşisi, proje issue tiplerini otomatik tespit.
- **Atlassian Confluence** — sayfa okuma (RAG bağlamı için) ve yazma
  (analiz yayımlama); Markdown → Confluence Storage Format dönüşümü.
- **Veri senkronizasyonu** — Confluence space'leri ve Jira projeleri yerel
  referans klasörüne senkronlanır; analizlerde otomatik bağlam olur.

---

## 8. Operasyonel / Teknik Özellikler

- **İnsan denetimi:** Her kritik adımda onay; AI hiçbir şeyi tek başına
  Jira'ya yazmaz — kullanıcı önizleyip seçer.
- **Kararlılık:** Log rotasyonu + eski log temizliği, atomik dosya yazımı,
  alt-süreç çökme/timeout kurtarma, zip-bomb koruması.
- **Güvenlik:** Oturum çerezi bayrakları, `.env` dosya izinleri (0600),
  `.env` asla versiyon kontrolüne girmez.
- **Kendi kendini güncelleme:** Uygulama GitHub'dan son sürümü
  `git pull --ff-only` ile güvenli biçimde çekebilir.
- **Geçmiş:** Son 5 çalıştırma arşivlenir.

---

## 9. AI Olgunluk Değerlendirmesi (özet tablo)

| Boyut | Durum |
|-------|-------|
| **Otomasyon kapsamı** | Uçtan uca: doküman → analiz → prototip → görev |
| **AI mimarisi** | RAG — kurumsal kaynaklarla zenginleştirilmiş üretim |
| **Halüsinasyon kontrolü** | Var — entity whitelist, kaynak etiketleme, açık sorular |
| **İnsan denetimi (HITL)** | Her kritik adımda onay; seçmeli Jira oluşturma |
| **İzlenebilirlik** | Aşamalar arası numaralı ID takibi |
| **Maliyet optimizasyonu** | Prompt caching, combined-output, retry |
| **Entegrasyon olgunluğu** | Jira + Confluence çift yönlü (OAuth) |
| **Özelleştirilebilirlik** | 15 sistem promptu arayüzden düzenlenebilir |
| **Dağıtım** | Tek tık masaüstü uygulaması (macOS) |

### Güçlü yönler
- Kurumsal bağlamı (mevcut API/DB/kod) analize katan gerçek bir RAG akışı
- Üretilen çıktının doğrudan geliştirmeye dökülebilir detayda olması
- İnsan onayının her aşamada korunması — kontrollü otomasyon

### Geliştirme alanları (yol haritası adayları)
- Tek input dosyası kısıtı (çoklu doküman desteği)
- Çıktı kalitesi için otomatik değerlendirme/puanlama mekanizması yok
- Sadece Atlassian ekosistemi (Azure DevOps, GitHub Issues vb. yok)
- macOS'a özel dağıtım (Windows/web dağıtımı yok)

---

*Bu döküman Analyst Studio'nun mevcut durumunu özetler; AI portföy
değerlendirmesi için hazırlanmıştır.*
