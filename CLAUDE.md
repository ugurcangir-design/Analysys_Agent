# brd-analyst-agent — Claude Code Context

## Proje Özeti
Flask + Python, port **5002**. BRD/süreç dokümanı → analiz → Jira task.
Tarayıcı SPA: `http://localhost:5002` | Başlat: `source venv/bin/activate && python app.py`

---

## Dosya Yapısı & Anahtar Fonksiyonlar

```
app.py          Flask sunucusu (1376 satır)
agent.py        Anthropic API çağrıları (907 satır)
jira_agent.py   Jira OAuth + task oluştur/güncelle + markdown→ADF
jira_auth.py    OAuth 3LO flow, OAUTH_SCOPE (Jira + Confluence)
run.py          Orchestrator — subprocess ile çağrılır
workflow.py     Durum makinesi
templates/
  index.html    SPA (1851 satır) — 4 sekme: Çalıştır/Output/Geçmiş/Ayarlar
input/          Yüklenen dosya (tek)
output/         Üretilen çıktılar
reference/
  confluence/   Atlassian sync → .md dosyalar
  jira/         Atlassian sync → .json dosyalar
  services/     Swagger/OpenAPI .json dosyalar
  ui-code/      Frontend kaynak kod referansı
  current-brd/  Aktif BRD (kapsam karşılaştırması için)
  sources.json  Confluence spaces + Jira projects listesi
  context_filter.json  Bağlam filtresi
history/        Son 5 çalıştırma arşivi
logs/           Günlük log dosyaları
```

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

## app.py — Kritik Bölümler

### Sabitler / Dizinler (satır 22-36)
```python
BASE_DIR, INPUT_DIR, OUTPUT_DIR, REF_DIR, HISTORY_DIR, LOG_DIR
UI_CODE_DIR, CONF_DIR, JIRA_REF_DIR, SERVIS_DIR
ALLOWED_OUTPUTS  # yeni output dosyası eklenince buraya da ekle
```

### Suspend / Heartbeat (satır ~260-285)
```python
_suspended = False          # UI overlay için
SUSPEND_SURE = 120          # saniye
_son_heartbeat              # timestamp
_heartbeat_izle()           # thread — 120s sessizlikte _suspended=True
```

### Atlassian API Helpers (satır 131-270)
```python
_env_oku() → dict           # .env'i okur, quote'ları striple
_atlassian_refresh()        # access token yeniler
_atlassian_get(path, cloud_id, service="jira"|"confluence")
_atlassian_post(path, body, cloud_id, service=...)
_fetch_confluence_space(space_key, cloud_id) → int  # sayfa sayısı
_fetch_jira_project(project_key, cloud_id) → int    # issue sayısı
```

### Veri Kaynakları Sync (satır ~1100-1163)
```python
SOURCES_PATH = REF_DIR / "sources.json"
_sync_state = {"running", "log", "last_sync", "error"}
_sync_lock   # threading.Lock
# Routes: GET/POST/DELETE /api/sources/confluence|jira, POST /api/sources/sync
```

### Jira Config / Test (satır ~1240)
```python
# /api/jira/test: önce statik (CLIENT_ID/SECRET/URL/PROJECT_KEY)
# sonra OAuth (ACCESS_TOKEN/CLOUD_ID) ayrı kontrol
```

---

## agent.py — Kritik Bölümler

### İçerik Limitleri (satır 63-75)
```python
MAX_CHARS_BRD=100_000, MAX_CHARS_GENEL=30_000
MAX_CHARS_UI=10_000, MAX_CHARS_UI_TOT=60_000
MAX_CHARS_REF=15_000, MAX_CHARS_REF_TOT=50_000
MAX_TOKENS_COMBINED=12_000, MAX_TOKENS_BRD_CMB=9_000, MAX_TOKENS_KAPSAM=8_000
```

### Modeller
```python
MODEL_ANALIZ = "claude-sonnet-4-6"   # tüm analizler
# jira_agent.py: başlık için claude-haiku-4-5-20251001
```

### Analiz Fonksiyonları
```python
surec_analizi_yap() → Path                    # surec-analizi.md
teknik_analiz_yap() → (Path, Path)            # teknik-analiz.md, acik-sorular.md
brd_analizi_yap()   → (Path, Path)            # brd-analizi.md, brd-sorular.md
kapsam_analizi_yap() → (Path, Path)           # kapsam-analizi.md, alternatif-surecler.md
yeniden_calistir(hedef, not) → Path           # mevcut çıktıyı güncelle
brd_final_kaydet() → Path                     # input → reference/current-brd/
```

### Combined XML Pattern (token tasarrufu ~%40)
```python
# Tek API çağrısında iki çıktı:
# <teknik_analiz>...</teknik_analiz><acik_sorular>...</acik_sorular>
_xml_ayir(text, tag) → str    # XML tag'den içerik çıkar
_metin_sikistir(metin) → str  # ardışık boş satırları temizle
```

### Bağlam Filtresi
```python
load_context_filter() → dict | None     # reference/context_filter.json
filtrele_referanslar(files, ctx) → list # keyword/jira_key/confluence_page filtresi
_filtrele_openapi_json(path, kws) → Path|None|False  # büyük Swagger'ları filtrele
```

### Prompt Caching
```python
# system prompt → cache_control: ephemeral (5dk önbellek)
# extra_headers: {"anthropic-beta": "prompt-caching-2024-07-31"}
# İlk çalıştırma yavaş (cache ısınıyor), sonrakiler ~%90 token tasarrufu
```

---

## jira_agent.py — Kritik Bölümler
```python
baslangic_kontrol()         # env değişkenlerini doğrular
jira_task_olustur()         # yeni task — ADF description
jira_task_guncelle(key)     # mevcut task'ı güncelle
markdown_to_adf(md) → dict  # markdown → Atlassian Document Format
main() → (task_key, basligi)
# Model: claude-haiku-4-5-20251001 (başlık üretimi için)
# Desteklenen: heading, paragraph, bulletList, orderedList, codeBlock, table, rule
# Inline: bold, italic, code, link
```

---

## jira_auth.py
```python
REDIRECT_URI = "http://localhost:5002/api/jira/callback"
OAUTH_SCOPE  = "read:jira-work write:jira-work read:jira-user offline_access
                read:confluence-space.summary read:confluence-content.all
                read:confluence-content.summary"
auth_url_olustur() → str    # Atlassian OAuth URL
auth_tamamla(code) → dict   # token al, cloud_id kaydet
```

---

## Mimari: subprocess + sys.stdin.isatty()
```
Tarayıcı → fetch /api/run → app.py → subprocess run.py {mod} → agent/jira
app.py /api/status ← polling 1.5s
not sys.stdin.isatty() → otomatik onay (GUI modunda input() çağrılmaz)
```

---

## Geliştirme Kuralları
1. **Türkçe** — print, yorum, hata metni; teknik terimler İngilizce
2. Yeni output dosyası → `ALLOWED_OUTPUTS` setine ekle (app.py)
3. Yeni Jira field → hem `jira_task_olustur()` hem `jira_task_guncelle()` güncelle
4. `sys.executable` kullan, Python yolunu hard-code etme
5. `_env_oku()` quote'ları strip eder — `.env`'deki `'value'` → `value`
6. Token tasarrufu: combined XML pattern kullan, referans limitlerini koru
7. `.env` asla commit edilmez

---

## Planlanan Geliştirmeler (Faz 2)

### Adım 0 — Skill Ayrıştırma ✅ TAMAMLANDI
```
skills/base.py           # dosya okuma, API çağrısı, XML parse, ortak yardımcılar
skills/surec_analizi.py
skills/teknik_analiz.py
skills/brd_analizi.py
skills/kapsam_analizi.py
skills/api_schema.py     # Adım 5 — OpenAPI YAML + DDL üretimi (YAPILACAK)
skills/confluence_yaz.py # Adım 6 — Confluence write (YAPILACAK)
skills/jira_tasks.py     # Adım 7 — Epic/Story/Subtask hiyerarşisi (YAPILACAK)
skills/html_mockup.py    # Adım 8 — HTML prototip üretimi (YAPILACAK)
```
`agent.py` = 12 satır import bridge. `run.py` değişmedi.

### Adım 1 — Confluence Yazma ✅ TAMAMLANDI
- `skills/atlassian.py` — env_oku, atlassian_refresh/get/post/put, confluence CRUD
- `skills/confluence_yaz.py` — md_to_storage(), confluence_yayimla()
- `POST /api/confluence/publish` — dosya + space_key alır, sayfa oluşturur/günceller
- UI: Output sekmesinde space dropdown + "Yayımla" butonu (space varsa görünür)

### Adım 2 — Jira Task Hiyerarşisi ✅ TAMAMLANDI
- `skills/jira_tasks.py` — teknik-analiz.md → AI JSON hiyerarşi → Epic+Story+Subtask
- `skills/atlassian.py` — atlassian_put + confluence CRUD (Adım 1'de oluşturuldu)
- `POST /api/jira/hierarchy` — dosya + opsiyonel confluence_url alır
- UI: teknik-analiz.md seçilince "⬆ Hiyerarşik Task Oluştur" butonu görünür
- Proje issue type'larını otomatik tespit eder (Epic/Story/Subtask veya Task/Subtask fallback)

### Adım 3 — API Şema & DDL ✅ TAMAMLANDI (prompt kalite iyileştirmesi)
- Ayrı dosya yok — teknik-analiz.md içinde Bölüm 3 ve 4 iyileştirildi
- Bölüm 3: gerçek CREATE TABLE DDL blokları (```sql) + index + FK kısıtları
- Bölüm 4: gerçek OpenAPI 3.0 YAML endpoint blokları (```yaml) + request/response şemaları
- MAX_TOKENS_COMBINED: 12_000 → 16_000 (daha uzun kod çıktısı için)
- Her bölüme format rehberi eklendi (risk tablosu, state machine, güvenlik checklist vb.)

### Adım 4 — HTML Prototip ✅ TAMAMLANDI
- `skills/html_mockup.py` — surec-analizi.md → output/mockup.html; ui-code/ varsa tasarım diline uyar
- `mockup_oku_kontekst()` — teknik_analiz.py'ye mockup özeti sağlar (style+body, max 20k)
- `POST /api/mockup/generate` — browser'dan tetikleyici
- `mockup.html` → `IZIN_VERILEN_CIKTILAR`'a eklendi; `/api/output/mockup.html` text/html döner
- UI: onay kutusunda "HTML Prototip Oluştur" butonu; Çıktılar sekmesinde "Prototip" tab + iframe görüntüleme + HTML editörü

---

## Bilinen Kısıtlamalar
- `markdown_to_adf` nested list'leri düzleştirir
- History limiti 5 (sabit, app.py `save_to_history()`)
- Tek input dosyası (birden fazla yüklenirse ilk kullanılır)
- Jira task tipi sabit `Task` (Story/Bug/Epic yok — Adım 2'de değişecek)
- Confluence sync: Confluence scopes OAuth'ta yeni eklendi → bir kez yeniden bağlan gerekebilir
