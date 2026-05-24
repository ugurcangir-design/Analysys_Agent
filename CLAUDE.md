# brd-analyst-agent — Claude Code Context

## Proje Özeti
**Analyst Studio** — macOS masaüstü uygulaması. BRD / süreç dokümanı →
RAG destekli analiz → Jira Epic/Story/Subtask. Flask + Python, port **5002**.
Tarayıcı SPA: `http://localhost:5002`
Başlatma: `source venv/bin/activate && python app.py` (veya Analyst Studio.app)

İki ana akış:
- **Süreç → Teknik → Jira:** ana akış (FE/BE katman ayrımıyla görev üretir)
- **BRD → Kapsam:** BRD analizi + kapsam karşılaştırması

---

## Dosya Yapısı

```
app.py                  Flask sunucusu (~2100 satır, 71 endpoint)
agent.py                13 satırlık import bridge — skills/ modüllerine yönlendirir
jira_agent.py           Jira OAuth + ADF (Atlassian Document Format) yardımcıları
jira_auth.py            OAuth 3LO flow (Jira + Confluence scope'ları)
run.py                  Orchestrator — subprocess ile çağrılır
workflow.py             Durum makinesi (RLock + atomik dosya yazımı)

skills/                 Asıl iş mantığı; agent.py buradan import eder
  __init__.py
  base.py               Sabitler, dosya okuma, API çağrısı, RAG, 15 sistem promptu
  atlassian.py          OAuth helper'ları (env_oku, atlassian_refresh/get/post/put) — CANONICAL
  surec_analizi.py      Süreç analizi
  teknik_analiz.py      Teknik analiz + açık sorular
  brd_analizi.py        BRD analizi + PO soruları + brd_final_kaydet
  kapsam_analizi.py     Kapsam karşılaştırması + alternatif süreçler
  html_mockup.py        HTML prototip üretimi + mockup_oku_kontekst
  jira_tasks.py         jira_hiyerarsi_uret (preview) + jira_hiyerarsi_olustur (create)
  confluence_yaz.py     md → Confluence Storage Format dönüşümü + yayımlama

templates/index.html    SPA (~4580 satır) — 4 sekme: Çalıştır / Çıktılar / Referanslar / Ayarlar

reference/
  confluence/<space>/   Atlassian sync — .md dosyalar
  jira/<project>.json   Atlassian sync — JSON issue listeleri
  services/             Swagger/OpenAPI .json/.yaml
  ui-code/              Frontend kaynak kod referansı (zip upload ile)
  current-brd/          Aktif baseline BRD (kapsam karşılaştırması için)
  sources.json          Confluence spaces + Jira projects listesi
  context_filter.json   Bağlam filtresi (keyword / jira_keys / confluence_pages)
  prompts.json          Kullanıcı prompt override'ları

input/                  Yüklenen tek dosya (PDF/DOCX/MD/TXT/PNG/JPG)
output/                 Üretilen çıktılar (aşağıdaki IZIN_VERILEN_CIKTILAR)
history/                Son 5 çalıştırma arşivi
logs/                   RotatingFileHandler — app.log; eski app-YYYYMMDD.log >30g otomatik silinir

PROJE-OZETI.md          AI portföy değerlendirmesi için özet
KILAVUZ.html            Ekip için kurulum + kullanım kılavuzu (self-contained HTML)
```

---

## Çıktı Dosyaları (output/, IZIN_VERILEN_CIKTILAR)
```
surec-analizi.md           teknik-analiz.md           acik-sorular.md
brd-analizi.md             brd-sorular.md
kapsam-analizi.md          alternatif-surecler.md
mockup.html                workflow-state.json
```
Yeni output dosyası eklenince `app.py`'deki `IZIN_VERILEN_CIKTILAR` set'ine de ekle.

---

## Workflow Durumları (workflow.py → Durum)
```
IDLE → SUREC_ANALIZI_CALISIYOR → ONAY_BEKLENIYOR
     → TEKNIK_ANALIZ_CALISIYOR → TEKNIK_ANALIZ_ONAY_BEKLENIYOR
     → BRD_REVIZE_BEKLENIYOR   → BRD_TAMAMLANDI
     → JIRA_GONDERILIYOR       → JIRA_TAMAMLANDI
     → HATA
```

---

## Sabitler / Limitler (skills/base.py)
```python
MODEL_ANALIZ = "claude-sonnet-4-6"   # tüm analizler
# jira_agent.py: claude-haiku-4-5    # Jira görev başlığı için (hafif iş)

# Karakter limitleri
MAX_CHARS_BRD     = 100_000
MAX_CHARS_GENEL   =  30_000
MAX_CHARS_UI      =  10_000
MAX_CHARS_UI_TOT  =  60_000
MAX_CHARS_REF     =  15_000   # dosya başına
# RAG için per-tip limitler (eski MAX_CHARS_REF_TOT=50_000 deprecated)
MAX_CHARS_CONF_TOT   = 80_000   # Confluence
MAX_CHARS_JIRA_TOT   = 60_000   # Jira (markdown formatında)
MAX_CHARS_SERVIS_TOT = 60_000   # Swagger/OpenAPI
MAX_CHARS_DIGER_TOT  = 20_000

# Token limitleri
MAX_TOKENS_UZUN     =  8_000
MAX_TOKENS_KISA     =  3_000
MAX_TOKENS_COMBINED = 16_000   # teknik analiz (DDL + OpenAPI YAML için)
MAX_TOKENS_BRD_CMB  =  9_000
MAX_TOKENS_KAPSAM   =  8_000
```

### Heartbeat / Suspend (app.py)
```python
SUSPEND_SURE = 30   # saniye — bu kadar heartbeat yoksa overlay göster
KAPAT_SURE   = 45   # saniye — DESKTOP_MODE'da SIGINT (refresh ile karışmasın)
```

### Retry (skills/base.py)
`_api_yeniden_dene` — 429/5xx/connection için exponential backoff (4s, 8s, 16s; 3 deneme).

---

## RAG Mimarisi (skills/base.py)

### Bağlam blokları
`_ref_bloklari_olustur(ref_dosyalar)` referansları **tipine göre gruplandırır**:
- `### CONFLUENCE DOKÜMANTASYONU` (md dosyalar)
- `### JİRA TASK GEÇMİŞİ` (`_jira_json_to_md` ile kompakt markdown'a çevrilir)
- `### API / SWAGGER TANIMLARI` (filtrelenmiş openapi)
- `### DİĞER REFERANSLAR`

Her tip ayrı limitle, başına bir context blok başlığı ile gönderilir.

### Bağlam filtresi
`load_context_filter()` → keyword / jira_keys / confluence_pages ile ön filtreleme.
`filtrele_referanslar(files, ctx)` — büyük Swagger için `_filtrele_openapi_json()` keyword bazlı kırpma yapar.

### Prompt caching
- System prompt → `cache_control: ephemeral`
- Stable user blocks (ref + UI + mockup) → cache breakpoint son bloğa eklenir
- `extra_headers: {"anthropic-beta": "prompt-caching-2024-07-31"}`
- İlk çağrı yavaş (cache ısınıyor); 5 dk içindeki tekrar çağrılar ~%90 token tasarrufu.

### Tüm analiz skillleri RAG kullanır
`surec_analizi`, `teknik_analiz`, `brd_analizi`, `kapsam_analizi` — hepsi
`referans_dosyalari_hazirla()` + `_ref_bloklari_olustur()` çağırır.

---

## 15 Sistem Promptu (skills/base.py → VARSAYILAN_PROMPTLAR)

Tutarlı yapı: `# ROL → GÖREV → ÇIKTININ AMACI → ÇALIŞMA YÖNTEMİ → RAG İLKESİ → BAĞLAM KULLANIMI → KALİTE ÖLÇÜTÜ`.

```
surec_analizi_rol            brd_analizi_rol            kapsam_analizi_rol
surec_analizi                brd_analizi_bolumler       kapsam_analizi_bolumler
teknik_analiz_rol            brd_analizi_sorular        kapsam_analizi_alternatifler
teknik_analiz_bolumler       html_mockup_base           refine
teknik_analiz_sorular        jira_tasks                 confluence_publisher
```

### EK KURALLAR (otomatik append)
`prompt_yukle()` şu 5 prompta `_ORTAK_EK_KURALLAR` ekler:
`surec_analizi`, `teknik_analiz_bolumler`, `kapsam_analizi_bolumler`,
`brd_analizi_bolumler`, `jira_tasks` (bkz. `_EK_KURAL_SKILL_IDS`).

`_ORTAK_EK_KURALLAR` 4 bölüm: Kaynak Önceliği, Kaynak İzleme `[K: ...]`,
Halüsinasyon Koruması (Entity Whitelist), İzlenebilirlik (aşama bazlı ID tablosu).

### Prompt override sistemi
`reference/prompts.json` — kullanıcı arayüzden düzenlerse buraya kaydedilir;
`prompt_yukle()` önce override'a bakar, yoksa VARSAYILAN_PROMPTLAR'dan döner.

---

## ID Şeması (aşamalar arası izlenebilirlik)
```
BRD Analizi    : FR-XXX  NFR-XXX  US-XXX  AC-XXX  I-XXX
Süreç Analizi  : A-XXX   PA-XXX   BR-XXX  AF-XXX  EF-XXX  AC-XXX  EK-XXX (ekran)
Teknik Analiz  : T-FE-XX  T-BE-XX (Bölüm 17 İş Kırılımı)
Kapsam Analizi : YE-XXX (yeni eklenen) KL-XXX (kaldırılan) DG-XXX (değiştirilen)
```

## FE / BE Katman Ayrımı
Süreç adımları, iş kuralları, ekranlar ve teknik iş öğeleri **katman etiketi**
taşır: `FE / BE / FE+BE / Tek tip`. Bu, FE ve BE Jira görevlerinin ayrı ama
ilişkili olarak açılmasını sağlar.

**Teknik analizde:**
- Bölüm 16 → Frontend (FE) Teknik Tasarımı (her zaman, koşulsuz)
- Bölüm 17 → İş Kırılımı (T-FE / T-BE tablosu — Jira temeli)

**Jira önizleme modalı** her Story/Subtask satırında `FE` / `BE` rozeti gösterir.

---

## Önemli Endpoint'ler (app.py — 71 toplam)

### Çalıştırma / Workflow
```
POST /api/run                  Analiz başlat
GET  /api/status               Workflow durumu (polling 1.5s)
POST /api/approve              Süreç analizi onayı
POST /api/approve-teknik       Teknik analiz onayı (jira ile)
POST /api/approve-teknik-no-jira
POST /api/reject(-teknik)      Reddet
POST /api/rerun                Düzeltme notu ile yeniden çalıştır
POST /api/reset                Workflow'u IDLE'a sıfırla
POST /api/heartbeat            UI canlı sinyali (every 20s)
POST /api/shutdown             DESKTOP_MODE'da sunucuyu kapat
```

### Çıktı / Referans
```
GET  /api/outputs              Mevcut çıktıları listele
GET  /api/output/<ad>          İçerik oku
POST /api/output/delete        Çıktıyı sil
GET  /api/reference/list       Referans dosya ağacı
POST /api/reference/upload/<kategori>
POST /api/reference/delete
GET  /api/reference/content
POST /api/reference/fetch-be   Backend'den içerik çek
```

### Jira
```
GET  /api/jira/auth-url        OAuth başlat
GET  /api/jira/callback        OAuth dönüş
POST /api/jira/test            Bağlantı testi
POST /api/jira/hierarchy/preview   AI hiyerarşi önerir (Jira'ya YAZMAZ)
POST /api/jira/hierarchy/create    Analist seçtiklerini Jira'da açar
```

### Confluence + diğer
```
POST /api/confluence/publish   Markdown → Confluence sayfası
POST /api/confluence/diagnose  Scope/erişim teşhisi
POST /api/mockup/generate      HTML prototip üret
POST /api/sources/sync         Confluence/Jira veri çek
GET  /api/git/status           GitHub güncelleme kontrolü
POST /api/git/pull             git pull --ff-only
GET  /api/prompts              15 prompt + override durumu
POST /api/prompts/<id>         Prompt özelleştirme kaydet
POST /api/prompts/<id>/reset   Varsayılana dön
GET  /api/context-filter
POST /api/context-filter
GET  /api/history              Son 5 çalıştırma arşivi
```

---

## Güvenlik Mimarisi

### Auth (opsiyonel — AUTH_ENABLED env ile aç/kapa)
- Varsayılan **kapalı** (kişisel masaüstü kullanımı için)
- Açıkken `session["username"]` üzerinden cookie-based auth
- Şifre hash: `werkzeug.security.generate_password_hash` (scrypt)
- `users.json` dosyasında saklanır; `manage_users.py` CLI ile eklenir
- Brute-force koruması: IP başına 5 deneme/60s (RAM'de)
- `_admin_mi()`: env `ADMIN_USER` ile eşleşen username admindir

### CSRF — Origin/Referer kontrolü
- `csrf_kontrol()` before_request: POST/PUT/PATCH/DELETE'te kaynak host_url ile eşleşmeli
- Eşleşmezse 403 + WARN log
- `CSRF_MUAF`: `/api/auth/login`, `/api/heartbeat`
- Belt-and-suspenders: `SESSION_COOKIE_SAMESITE=Lax` zaten cross-site POST'a cookie göndermez

### Admin Yetkisi (@admin_gerekli decorator)
Sadece yapılandırma/yönetim endpoint'lerinde:
- `POST /api/prompts/<id>` (AI davranışı)
- `POST /api/prompts/<id>/reset`
- `POST /api/git/pull` (uygulama güncelleme)
- `POST /api/reset` (workflow zorla sıfırla)
- AUTH kapalıyken decorator otomatik geçer (kişisel mod = herkes admin)

### Başlangıç Güvenlik Kontrolü
`_baslangic_guvenlik_kontrol()`:
- **Default `HOST=127.0.0.1`** (yalnız yerel)
- LAN'a açmak için `.env`'de `HOST=0.0.0.0`
- LAN açık + AUTH kapalı → uygulama BAŞLATILMAZ (3 çözüm önerisi gösterir)
- Override: `ALLOW_LAN_NO_AUTH=true` (bilinçli risk kabulü)

### Diğer
- `SESSION_COOKIE_HTTPONLY=True`, `SAMESITE=Lax`
- `SESSION_COOKIE_SECURE` env ile açılır (HTTPS deploy için)
- CSP, X-Frame-Options, X-Content-Type-Options başlıkları (`guvenlik_basliklari`)
- iframe sandbox: `allow-scripts allow-forms` (NO `allow-same-origin` → AI mockup parent DOM'a erişemez)
- `.env` chmod 0600, atomik yazım (tmp.replace)
- Path traversal: `_guvenli_yol()` helper'ı tüm dosya yolu girdilerinde kullanılır

---

## Mimari: subprocess + sys.stdin.isatty()
```
Tarayıcı → fetch /api/run → app.py → subprocess.Popen(run.py {mod})
                                  ↓
                          run.py → skills/* modülleri → Claude API
app.py /api/status ← polling 1.5s, workflow.py durum okur
not sys.stdin.isatty() → GUI modu (input() çağrılmaz, otomatik onay)
```

### Subprocess kararlılığı
- `encoding="utf-8", errors="replace", start_new_session=True`
- `_bekle()` thread'i timeout/crash'i yakalar, workflow'u HATA'ya çeker
- Zip yükleme: zip-bomb koruması (compression ratio > 100 atla)

---

## CLAUDE.md Bakım Kuralı (zorunlu)
**Her commit sonrası CLAUDE.md güncel kalmalı.** Eğer commit şu konulardan
birini etkiliyorsa, aynı commit'te (veya hemen takip eden commit'te)
CLAUDE.md'yi de güncelle ve push et:
- Dosya yapısı / yeni veya kaldırılan modül
- Skill modüllerinin sorumlulukları
- Endpoint'ler (yeni / kaldırılan / yol değişikliği)
- Sabitler / limitler / model adı / heartbeat değerleri
- Sistem promptları / EK KURALLAR / ID şeması
- FE/BE katman akışı veya workflow durumları
- Geliştirme kuralları / bilinen kısıtlamalar

Sadece görsel/CSS/typo değişiklikleri için atlanabilir.

`.claude/hooks/post-commit-reminder.py` her `git commit`'ten sonra
otomatik hatırlatma üretir; ancak nihai sorumluluk Claude'dadır.

---

## Geliştirme Kuralları
1. **Türkçe** — print, yorum, hata metni; teknik terimler İngilizce
2. Yeni output dosyası → `IZIN_VERILEN_CIKTILAR` set'ine ekle (app.py)
3. Yeni Jira field → `jira_agent.py` ve `skills/jira_tasks.py` güncelle
4. `sys.executable` kullan, Python yolunu hard-code etme
5. `env_oku()` quote'ları strip eder — `.env`'deki `'value'` → `value`
6. Token tasarrufu: combined XML pattern + prompt caching + referans limitleri
7. **`.env` asla commit edilmez** (chmod 600, .gitignore'da)
8. Atlassian helper'ları **`skills/atlassian.py`'den import et** — app.py'de duplicate tanım yok
9. Prompt değiştirmek için: `VARSAYILAN_PROMPTLAR` (base.py) veya
   `reference/prompts.json` (override) — her ikisi geçerli, override öncelikli
10. Yeni prompt EK KURALLAR almasını istiyorsan `_EK_KURAL_SKILL_IDS`'e ekle

---

## Bilinen Kısıtlamalar
- `markdown_to_adf` nested list'leri düzleştirir
- History limiti **5** (sabit, app.py `save_to_history()`)
- Tek input dosyası (birden fazla yüklenirse ilk kullanılır)
- Atlassian-only — Azure DevOps, GitHub Issues entegrasyonu yok
- macOS-only dağıtım (Windows/Linux için manual setup gerekir)
- Çıktı kalitesi için otomatik değerlendirme/puanlama mekanizması yok

---

## Tamamlanan İşler (referans için)

### Faz 1 — Skill ayrıştırma ✅
`agent.py` → 13 satırlık import bridge; tüm iş mantığı `skills/` altında.

### Faz 2 ✅
- **Confluence yazma:** `skills/confluence_yaz.py` + Markdown→Storage Format
- **Jira hiyerarşi:** `skills/jira_tasks.py` — preview/create iki adımlı, FE/BE katman, modal seçim
- **API Şema & DDL:** teknik analiz Bölüm 3 (CREATE TABLE) ve Bölüm 4 (OpenAPI YAML)
- **HTML Prototip:** `skills/html_mockup.py` + mockup.html çıktısı

### Faz 3 (bu session) ✅
- **Deduplication:** atlassian helper'ları tek noktaya (skills/atlassian.py)
- **RAG tüm analizlerde:** `brd_analizi` ve `kapsam_analizi`'ne referans entegrasyonu
- **Jira JSON → kompakt markdown:** `_jira_json_to_md` ile ~%40 token tasarrufu
- **Tip bazlı ref bölümleri:** Confluence/Jira/Swagger ayrı bloklar, ayrı limitler
- **FE/BE katman ayrımı:** süreç → teknik → Jira boyunca; modal FE/BE rozeti
- **15 promptun yeniden yazımı:** ROL/GÖREV/ÇALIŞMA YÖNTEMİ/RAG İLKESİ yapısı
- **EK-XXX, T-FE/T-BE, FR/NFR/US/I, YE/KL/DG** yeni ID tipleri
- **`_ORTAK_EK_KURALLAR` güncellemesi:** aşama bazlı ID tablosu, FE/BE katman
- **Stabilite:** log rotation + eski log temizliği, atomik .env yazımı (chmod 600),
  subprocess crash recovery, API retry (exponential backoff), session cookie flags,
  zip-bomb koruması
- **GitHub self-update:** /api/git/status + /api/git/pull (sadece güncelleme sayfasında)
- **Heartbeat fix:** Cmd+Shift+R refresh'te uygulama kapanmıyor; SUSPEND_SURE=30s, KAPAT_SURE=45s
- **Belgeleme:** `PROJE-OZETI.md` (AI portföy) + `KILAVUZ.html` (ekip kılavuzu)
