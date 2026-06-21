# brd-analyst-agent — Claude Code Context

## Proje Özeti
**Analyst Studio** — macOS masaüstü uygulaması. BRD / süreç dokümanı →
RAG destekli analiz → Jira Epic/Story/Subtask. Flask + Python (**3.10+ zorunlu**, `str|None` tipleri), port **5002**.
Tarayıcı SPA: `http://localhost:5002`
Kurulum: `bash setup.sh` (önerilir) · Başlatma: `./start.sh` veya Analyst Studio.app
AI modu: **Pilot ekibi CLI modu kullanıyor** (`USE_CLAUDE_CLI=true`) — Claude.ai
aboneliği, per-token ücret yok. API modu (`ANTHROPIC_API_KEY`) alternatif/ikincil.
⚠ CLI modu görsel (PNG/JPG) BRD'yi analiz edemez — `_api_cagri_cli` net hata verir
(ekip BRD'leri PDF/DOCX/MD/TXT olmalı).
⚠ CLI çağrısı `--output-format json` kullanır (text DEĞİL) — text uzun/çok-turn
yanıtta çıktının başını kaybediyordu. json `result` tam döner; stop_reason/is_error
ile kesilme tespiti yapılır.
claude bulma: `_claude_yolu_bul()` PATH'e bağımlı değil — GUI .app minimal PATH
sorunu için nvm/~.local/homebrew konumlarını da tarar.

İki ana akış:
- **Süreç → Teknik → Jira:** ana akış (FE/BE katman ayrımıyla görev üretir)
- **BRD → Kapsam:** BRD analizi + kapsam karşılaştırması

---

## Dosya Yapısı

```
app.py                  Flask sunucusu (~2200 satır, 80 endpoint)
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
  teknik_analiz.py      Teknik analiz (ÜÇ AŞAMALI: teknik analiz → kapsam denetimi+AI denetçi → açık sorular)
  brd_analizi.py        BRD analizi + PO soruları + brd_final_kaydet
  kapsam_analizi.py     Kapsam karşılaştırması + alternatif süreçler
  html_mockup.py        HTML prototip üretimi + mockup_oku_kontekst
  jira_tasks.py         jira_hiyerarsi_uret (preview) + jira_hiyerarsi_olustur (create)
  jira_gorevleri.py     Epic/Story alt görevlerini çek + sınıflandır (yapısal+AI); standart formatla / teknik analiz et / Jira'ya yaz
  confluence_yaz.py     md → Confluence Storage Format dönüşümü + yayımlama
  sorular.py            Soru defteri: parse + storage + refine entegrasyonu

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
docs/                   CLAUDE.md'den ayrılan referans detayı:
  ENDPOINTS.md            Tam endpoint kataloğu (~80)
  GUVENLIK-DAGITIM.md     Auth/CSRF/admin + dağıtım + onboarding
  DEGISIKLIK-GECMISI.md   Tamamlanan işler / faz geçmişi
```

---

## Çıktı Dosyaları (output/, IZIN_VERILEN_CIKTILAR)
```
surec-analizi.md           teknik-analiz.md           acik-sorular.md
brd-analizi.md             brd-sorular.md
kapsam-analizi.md          alternatif-surecler.md
mockup.html                workflow-state.json        sorular.json
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
**Otomatik kurtarma:** `baslat()`/`baslat_teknik()` yalnız CALISMA_DURUMLARI'nda
reddeder; HATA/bekleme/tamamlanmış durumlardan temiz başlar (elle sıfırlama
gerekmez). Stale CALISIYOR (state çalışıyor der ama subprocess yok):
`_stale_workflow_kurtar()` run/run-teknik'te + startup'ta otomatik sıfırlar.

---

## Sabitler / Limitler (skills/base.py)
```python
MODEL_ANALIZ = "claude-sonnet-4-6"   # tüm analizler
MODEL_HAFIF  = "claude-haiku-4-5"    # hafif iş (jira_gorevleri: Standart Formatla,
                                     # açık sorular; jira_agent: görev başlığı)

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
MAX_TOKENS_UZUN     = 16_000   # süreç analizi (8K kesiyordu)
MAX_TOKENS_KISA     =  3_000
MAX_TOKENS_COMBINED = 16_000   # teknik analiz (DDL + OpenAPI YAML için)
MAX_TOKENS_BRD_CMB  =  9_000
MAX_TOKENS_KAPSAM   =  8_000
```

### Heartbeat / Suspend (app.py)
```python
SUSPEND_SURE = 30    # saniye — bu kadar heartbeat yoksa overlay göster
KAPAT_SURE   = 180   # saniye — DESKTOP_MODE'da kapat. 180s: Chrome arka plan
                     # throttling'ine (1 hb/dk) dayanıklı. Analiz sürerken
                     # ASLA kapanmaz (_analiz_calisiyor_mu guard).
                     # SIGINT 10s'de işe yaramazsa os._exit(0) — zombi önleme.
# Heartbeat UI: 20s interval (arka planda da gönderilir) + visibilitychange'te anında
```

### Retry (skills/base.py)
`_api_yeniden_dene` — 429/5xx/connection için exponential backoff (4s, 8s, 16s; 3 deneme).

### Çıktı Önbelleği (skills/base.py — token tasarrufu, 429 çare)
`_api_cagri` içerik-hash'li önbellek: aynı (sistem prompt + mesajlar + model + limit)
→ kaydedilen yanıt, **0 token**. İçerik değişince (doküman/referans/filtre/prompt)
anahtar değişir → taze çağrı. Refine'in düzeltme notu prompt'u değiştirdiği için
doğal cache-miss. Depo: `.api_cache/` (gitignored). Kapat: `.env` `API_CACHE=false`,
TTL: `API_CACHE_TTL` (vars. 7 gün).

### Yönetici Özeti / TL;DR (skills/base.py)
`yonetici_ozeti_olustur()` süreç & teknik analiz çıktısının EN ÜSTÜne deterministik
(0 token) özet ekler: kapsam (endpoint/tablo/bölüm), süreç kapsam %'si, açık soru
(kritik) sayısı. **Jira'ya YAZILMAZ** — `yonetici_ozetini_cikar()` her Jira yazma
yolunda (jira_tasks hiyerarşi + gorev_jiraya_yaz) çağrılır.

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

## 16 Sistem Promptu (skills/base.py → VARSAYILAN_PROMPTLAR)

Tutarlı yapı: `# ROL → GÖREV → ÇIKTININ AMACI → ÇALIŞMA YÖNTEMİ → RAG İLKESİ → BAĞLAM KULLANIMI → KALİTE ÖLÇÜTÜ`.

```
surec_analizi_rol            brd_analizi_rol            kapsam_analizi_rol
surec_analizi                brd_analizi_bolumler       kapsam_analizi_bolumler
teknik_analiz_rol            brd_analizi_sorular        kapsam_analizi_alternatifler
teknik_analiz_bolumler       html_mockup_base           refine
teknik_analiz_sorular        jira_tasks                 confluence_publisher
teknik_analiz_denetci
```
`teknik_analiz_denetci` (Aşama 3 denetçi) `_ORTAK_EK_KURALLAR` ALMAZ — sadece
sorun tespit eder, içerik üretmez. UI prompt editöründe `_PROMPT_GRUPLARI`
(index.html) "Süreç / Teknik Analiz" grubuna ekli.

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
Teknik Analiz  : T-FE-XX  T-BE-XX (Bölüm 2/5/7'den çıkarılan FE/BE görevleri)
Kapsam Analizi : YE-XXX (yeni eklenen) KL-XXX (kaldırılan) DG-XXX (değiştirilen)
```

## FE / BE Katman Ayrımı
Süreç adımları, iş kuralları, ekranlar ve teknik iş öğeleri **katman etiketi**
taşır: `FE / BE / FE+BE / Tek tip`. Bu, FE ve BE Jira görevlerinin ayrı ama
ilişkili olarak açılmasını sağlar.

**Teknik analizde (kullanıcının 12 bölümlük şablonu):**
- Bölüm 7 → Frontend İş Kırılımı (FE bileşen/state/API/validasyon; FE işi yoksa boş bölüm notu)
- Bölüm 2 (İş Gereksinimleri) + 5 (API Tasarımı) → BE/işlevsel görevler; Jira hiyerarşisi bu bölümlerden çıkarılır

**Jira önizleme modalı** her Story/Subtask satırında `FE` / `BE` rozeti gösterir.

---

## Endpoint'ler & Jira Görevleri Özelliği

**Tam endpoint kataloğu (~80 endpoint): [docs/ENDPOINTS.md](docs/ENDPOINTS.md)** —
endpoint ekleyince/kaldırınca orayı güncelle. Aşağıda yalnızca en yeni/karmaşık
özelliğin mimarisi özetlenir.

### Jira Görevleri (`skills/jira_gorevleri.py` + UI `page-jira-gorevler`)
Doküman yüklemeden, **mevcut** bir Jira Epic/Story altındaki görevleri çekip triyaj eder.

- **Çekme:** `alt_gorevleri_cek` üç bağ modelini birleştirir (tekrarsız): `parent = KEY`
  (sub-task), `"Epic Link" = KEY` (epic), `issue in linkedIssues(KEY)` (Relates — bazı
  ekipler hiyerarşi yerine bunu kullanır). Görev yorumları (ADF→metin) da çekilir.
- **İki fazlı sınıflandırma** (token/timeout için):
  - FAZ 1 (`/cek`, `ai_kullan=False`): yalnızca **yapısal ön-tarama** (`_yapisal_skor` —
    bölüm/dosya işaretleri), anında, 0 token. Kartta `kaynak=yapisal`.
  - FAZ 2 (`/siniflandir`, "AI ile Sınıflandır"): AI **HER görevi içerikten** okuyup
    gerekçeyle sınıflandırır (parçalı). `kaynak=ai`. Opt-in, token harcar.
- **Benzer içerik:** `benzer_gorevleri_isaretle` Jaccard (eşik 0.35, 0 token) → kartta
  sarı uyarı + tıklanabilir link.
- **İki aksiyon-grubu:** *Hızlı İşleme Alınacak* → **Standart Formatla** (Özellik 1, 4 başlık,
  **Haiku**); *Detaylı Analiz Gerekir* → **Teknik Analiz Et** (Özellik 2 — Sonnet teknik
  analiz [RAG + Süreç ekranındaki **bağlam filtresi** dahil] + ayrı **Haiku** açık-sorular
  pass'i; modal'da ikinci sekme, Jira'ya yazılmaz).
- **UI:** arama/filtre, katlanabilir gruplar, tam ekran **modal** (`.jg-modal`, Esc), Jira
  sekmesinde üst bar kendi durumunu gösterir (`_jgTabAktif`). **Onayla** → `gorev_jiraya_yaz`
  Jira description'ı ÜZERİNE YAZAR (atlassian_put + markdown_to_adf; HTML yorumları silinir).

Soru Defteri durumları: `acik / bekleniyor / cevaplandi / atlandi / varsayim`
(kalıcı: `output/sorular.json`, atomik yazım).

---

## Güvenlik & Dağıtım

Detay: **[docs/GUVENLIK-DAGITIM.md](docs/GUVENLIK-DAGITIM.md)** (auth, CSRF, admin yetkisi,
başlangıç güvenlik kontrolü, dağıtım modeli, onboarding). Özet:
- **Birincil dağıtım:** lokal kurulum (her analist kendi makinesinde). Sunucu modu deneysel/deprecated.
- **Default `HOST=127.0.0.1`**; LAN açık + AUTH kapalı → uygulama BAŞLATILMAZ.
- CSRF Origin/Referer kontrolü (`csrf_kontrol`), path traversal koruması (`_guvenli_yol`),
  `.env` chmod 0600 + atomik yazım, CSP/X-Frame-Options.
- Güvenlik/auth kod yolu değişirse o dosyayı da güncelle.

---

## Mimari: subprocess + sys.stdin.isatty()
```
Tarayıcı → fetch /api/run → app.py → subprocess.Popen(run.py {mod})
                                  ↓
                          run.py → skills/* modülleri → Claude API
app.py /api/workflow-state ← polling 1.5s, workflow.py durum okur
not sys.stdin.isatty() → GUI modu (input() çağrılmaz, otomatik onay)
```

### Subprocess kararlılığı
- `encoding="utf-8", errors="replace", start_new_session=True`
- `_bekle()` thread'i timeout/crash'i yakalar, workflow'u HATA'ya çeker
- Zip yükleme: zip-bomb koruması (compression ratio > 100 atla)
- **Teknik analiz ÜÇ AŞAMALI** (`teknik_analiz_yap` → tuple(teknik_yol, sorular_yol)):
  1. Aşama 1: teknik analiz 1-11. bölümler (kullanıcının şablonu: Amaç/Hedefler,
     İş Gereksinimleri, Teknik Gereksinimler, Veritabanı, API, İş Mantığı,
     Frontend İş Kırılımı, Role Management, Hata Yönetimi, Teknik Borç/Riskler,
     Kabul Kriterleri). 12. bölüm "Karar Bekleyen Konular" güvenlik ağı regex'iyle
     prompttan çıkarılır → `teknik-analiz.md` (ham) BİTER BİTMEZ kaydedilir
  2. Aşama 3 (denetim): `surec_id_kapsam()` (base.py) deterministik olarak süreç
     ID'lerinin (BR/AC/PA/EF/EK) teknik analizde referans edilip edilmediğini
     denetler. Ardından `_teknik_denetle()` (prompt `teknik_analiz_denetci`)
     AI denetçi pass'i: kaynaksız iddia, §5↔§7 validasyon drift'i, uydurma
     endpoint/tablo, hata tutarsızlığı tarar. Kapsam özeti + denetçi bulguları
     `## 🔍 Otomatik Denetim Notları` olarak teknik-analiz.md SONUNA eklenip
     yeniden kaydedilir. Denetçi başarısız olursa ham teknik analiz korunur (try/except).
  3. Aşama 2: ayrı `_api_cagri` — ham Aşama 1 çıktısı + süreç analizi girdi alınıp
     "Karar Bekleyen Konular" / açık sorular üretilir → `acik-sorular.md`
     (`### Q-T-NNN:` blok formatı, UI parser uyumlu). Kapsam denetiminde
     karşılanmayan ID'ler Aşama 2'ye verilip GARANTİLİ açık soruya dönüştürülür.
     Aşama 2 başarısız olsa bile teknik analiz korunur (try/except → dosyaya hata notu).
  - **Boş bölüm kuralı:** kapsam yoksa (FE işi yok, yeni tablo yok vb.) bölüm
    uydurulmaz; başlık + tek satır not yazılır.
  - **Kesilme koruması:** CLI uzun analizi bazen erken bitiriyordu (doküman ~9.
    bölümde yarım kaydoluyordu). `_teknik_uret_tam()` Aşama 1 yanıtında kapanış
    `</teknik_analiz>` yoksa kesilmiş sayar ve yeniden dener (max 2); başaramazsa
    en dolu çıktıyı kaydedip uyarır. `_xml_ayir` (base.py) kapanış etiketi yoksa
    yarımı stray-etiketsiz kurtarır — tüm XML çıktı ayrıştırıcıları için geçerli.
- **Timeout katmanları** (CLI tam çıktıda yavaş):
  - `_api_cagri_cli` claude CLI: **1200s** (20 dk) · API SDK client: 1200s
  - app.py `_bekle` subprocess: **1320s** (22 dk) — CLI'dan FAZLA olmalı ki
    claude timeout'u önce tetiklenip net hata dönsün

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

**Referans detayı `docs/`'a ayrıldı** — endpoint değişikliği → `docs/ENDPOINTS.md`;
auth/güvenlik/dağıtım → `docs/GUVENLIK-DAGITIM.md`; faz/özellik bitince
→ `docs/DEGISIKLIK-GECMISI.md`. CLAUDE.md ana yapı/işlev + en yeni özellik özetini tutar.

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
- **CLI modu görsel (PNG/JPG) analiz edemez** — text-only. `_api_cagri_cli`
  görsel blok görürse net hata verir. Görsel BRD için API modu gerekir.
- `markdown_to_adf` nested list'leri düzleştirir
- History limiti **5** (sabit, app.py `save_to_history()`)
- Tek input dosyası (birden fazla yüklenirse ilk kullanılır)
- Atlassian-only — Azure DevOps, GitHub Issues entegrasyonu yok
- macOS-only dağıtım (Windows/Linux için manual setup gerekir)
- Tek aktif analiz (sunucu modunda) — lokal kurulumda her makine bağımsız

---

## Tamamlanan İşler / Değişiklik Geçmişi

Tarihsel kayıt (Faz 1-4): **[docs/DEGISIKLIK-GECMISI.md](docs/DEGISIKLIK-GECMISI.md)**.
Büyük bir faz/özellik tamamlandığında oraya özet ekle.
