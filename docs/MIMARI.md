# Mimari & İç İşleyiş — Detaylı Referans

> CLAUDE.md'den ayrılan detay. İlgili alanda çalışırken oku; her istekte gerekmez.

## Çıktı Dosyaları (output/, `IZIN_VERILEN_CIKTILAR`)
```
surec-analizi.md   teknik-analiz.md   acik-sorular.md
brd-analizi.md     brd-sorular.md     kapsam-analizi.md   alternatif-surecler.md
mockup.html        workflow-state.json   sorular.json
test-senaryolari.md   izlenebilirlik-matrisi.md   delta-analizi.md
```
Yeni output dosyası → `app.py` `IZIN_VERILEN_CIKTILAR` set'ine ekle.

## Analiz Zenginleştirmeleri (benzer-agent araştırmasından; Kiro/BMAD/Copilot4DevOps esinli)
- **Belirsizlik Denetimi** (`belirsizlik_denetimi`, base.py — 0 token, deterministik regex):
  muğlak Türkçe ifadeleri ("hızlı", "kolay", "vb.", "gerektiğinde"…) satır no + nedenle raporlar;
  kod blokları/HTML yorumları atlanır, max 20 bulgu. Süreç + teknik + delta çıktılarının sonuna
  "🔎 Belirsizlik Denetimi" bölümü olarak eklenir.
- **İzlenebilirlik Matrisi / RTM** (`izlenebilirlik_matrisi_olustur`, base.py — 0 token):
  süreç ID'si ↔ teknik analizde geçtiği bölüm başlıkları tablosu → `izlenebilirlik-matrisi.md`.
  Süreç metninde ID yoksa (özel prompt çıktısı) üretilmez.
- **Test Senaryoları / Gherkin** (`_test_senaryolari_uret`, teknik_analiz.py — MODEL_HAFIF/Haiku):
  kabul kriterleri + canlı gözlem kayıtlarından Diyelim ki/Eğer ki/O zaman senaryoları →
  `test-senaryolari.md`. Prompt: `test_senaryolari`. Hata pipeline'ı bozmaz (try/except).
- **CR / Delta Analizi** (`skills/delta_analizi.py` + `POST /api/delta-analiz` + UI paneli):
  mevcut teknik-analiz.md (zorunlu) + CR metni → yalnızca DELTA raporu (etkilenen bölümler,
  DBR-XXX değişen gereksinimler, regresyon riski) → `delta-analizi.md`. SENKRON çalışır
  (jira_gorev_analiz deseni — workflow durum makinesine girmez; çalışan analiz varsa 409).
  Referanslar + canlı gözlem (Bağlam Filtresi) delta'da da geçerli. Prompt: `delta_analizi`.
- **Mermaid süreç diyagramı**: süreç analizi promptuna otomatik ek talimat (varsayılan yolda) —
  Süreç Adımları sonuna `flowchart TD` bloğu (≤12 düğüm, PA-XXX etiketli). SPA'da mermaid@10 CDN +
  `mermaidRender()` tüm markdown görüntüleyicilerde (çıktı/önizleme/history) SVG render eder;
  bozuk diyagram metin olarak kalır (try/catch).

## Workflow Durumları (`workflow.py → Durum`)
```
IDLE → SUREC_ANALIZI_CALISIYOR → ONAY_BEKLENIYOR
     → TEKNIK_ANALIZ_CALISIYOR → TEKNIK_ANALIZ_ONAY_BEKLENIYOR
     → BRD_REVIZE_BEKLENIYOR   → BRD_TAMAMLANDI
     → JIRA_GONDERILIYOR       → JIRA_TAMAMLANDI → HATA
```
**Otomatik kurtarma:** `baslat()`/`baslat_teknik()` yalnız CALISMA_DURUMLARI'nda reddeder;
HATA/bekleme/tamamlanmış durumlardan temiz başlar. Stale CALISIYOR (state çalışıyor der ama
subprocess yok — örn. uygulama analiz ortasında kapandı/çöktü): `_stale_workflow_kurtar()`
`/api/run`, `/api/run-teknik` **ve** `GET /api/workflow-state`'te çağrılır. Üçüncüsü kritik:
UI bu uç noktayı birkaç saniyede bir poll edip `busy` durumuna göre Başlat butonunu
disable ediyor (`updateUI()` → `btn-surec.disabled = busy || !selectedFiles.surec`); yalnızca
run/run-teknik'te temizlense stale durum kalıcı olurdu çünkü buton disabled kaldığı için
kullanıcı hiç `/api/run`'a basamaz — kendini düzelten kod hiç tetiklenmezdi (tavuk-yumurta).
Artık her poll'da kontrol edilip ilk fırsatta sıfırlanıyor.

## Sabitler / Limitler (`skills/base.py`)
```python
MODEL_ANALIZ = "claude-sonnet-4-6"   # tüm analizler
MODEL_HAFIF  = "claude-haiku-4-5"    # hafif iş (jira_gorevleri Standart Formatla, açık sorular; jira_agent görev başlığı)

# Karakter limitleri
MAX_CHARS_BRD=100_000  MAX_CHARS_GENEL=30_000
MAX_CHARS_REF=15_000   # dosya başına
MAX_CHARS_CONF_TOT=80_000  MAX_CHARS_JIRA_TOT=60_000  MAX_CHARS_SERVIS_TOT=60_000
MAX_CHARS_LIVE_APP_TOT=60_000  MAX_CHARS_DIGER_TOT=20_000

# Token limitleri
MAX_TOKENS_UZUN=16_000  (süreç analizi)   MAX_TOKENS_KISA=3_000
MAX_TOKENS_COMBINED=16_000  (teknik; DDL+OpenAPI)   MAX_TOKENS_BRD_CMB=9_000   MAX_TOKENS_KAPSAM=8_000
```

### Heartbeat / Suspend (`app.py`)
`SUSPEND_SURE=30s` (overlay göster) · `KAPAT_SURE=180s` (DESKTOP_MODE'da kapat; Chrome arka-plan
throttling'e dayanıklı; analiz sürerken `_analiz_calisiyor_mu` guard'ı ile ASLA kapanmaz; SIGINT
10s'de işe yaramazsa `os._exit(0)`). UI heartbeat: 20s interval + visibilitychange'te anında.

### Retry (`_api_yeniden_dene`)
429/5xx/connection için exponential backoff (4s, 8s, 16s; 3 deneme).

### Çıktı Önbelleği (`_api_cagri`, token tasarrufu / 429 çare)
İçerik-hash'li önbellek: aynı (sistem prompt + mesajlar + model + limit) → kaydedilen yanıt, 0 token.
İçerik değişince taze çağrı. Refine'in düzeltme notu doğal cache-miss. `_api_cagri(..., onbellek=False)`
okumayı atlar ama yazar — kesik-çıktı retry'ı (`_teknik_uret_tam` 2+ deneme) ve refine bunu kullanır.
Depo: `.api_cache/` (gitignored), oturum başına süresi geçenler temizlenir. Kapat: `.env API_CACHE=false`,
TTL: `API_CACHE_TTL` (vars. 7 gün).

### Yönetici Özeti / TL;DR (`yonetici_ozeti_olustur`)
Süreç & teknik analiz çıktısının EN ÜSTÜne deterministik (0 token) özet: kapsam (endpoint/tablo/bölüm),
süreç kapsam %'si, açık soru (kritik) sayısı. **Jira'ya YAZILMAZ** — `yonetici_ozetini_cikar()` her Jira
yazma yolunda (jira_tasks hiyerarşi + gorev_jiraya_yaz) çağrılır.

## RAG Mimarisi (`skills/base.py`)
- **Bağlam blokları:** `_ref_bloklari_olustur(ref_dosyalar)` tipine göre gruplar — `### CONFLUENCE
  DOKÜMANTASYONU` (md), `### JİRA TASK GEÇMİŞİ` (`_jira_json_to_md` kompakt md), `### API / SWAGGER
  TANIMLARI` (filtrelenmiş openapi), `### CANLI UYGULAMA GÖZLEMİ` (`reference/live-app`),
  `### DİĞER REFERANSLAR`. Her tip ayrı limitle.
- **Bağlam filtresi:** `load_context_filter()` → keyword / jira_keys / confluence_pages ön-filtre +
  `live_app.target_url`, en fazla 5 `live_app.extra_urls` ve `live_app.use_as_sample`; `filtrele_referanslar(files, ctx)`
  büyük Swagger'ı `_filtrele_openapi_json()` ile keyword bazlı kırpar.
- **Canlı uygulama MCP/Chrome:** Süreç ve teknik analizde `canli_uygulama_baglami_hazirla()` URL listesi
  doluysa Claude Code'a ana URL'den başlayarak ekranı simüle etme, validasyon/mesaj/akışları ve network
  servislerini toplama görevi verir. MCP gözlem çıktıları `reference/live-app/` altına `.md/.json/.html`
  olarak bırakılırsa RAG'e `CANLI UYGULAMA GÖZLEMİ` bloğu olarak girer. Gizli header/token/cookie değerleri
  maskelenmelidir; kaynak etiketleri `[K: Canlı UI:<route>]` ve `[K: Network:<METHOD> <path>]`.
  `use_as_sample=true` ise ana URL süreç analizinde örnek ekran kabul edilir ve isterler ekran yapısına göre
  detaylandırılır. Ham UI kaynak kodu okuma/yükleme arayüzü kaldırılmıştır.
- **Prompt caching:** system prompt → `cache_control: ephemeral`; stable user blocks (ref+MCP hedefleri+mockup) son
  bloğa cache breakpoint; `anthropic-beta: prompt-caching-2024-07-31`. 5 dk içi tekrar ~%90 tasarruf.
  THINKING yolunda da aktif (`_api_cagri_direct`) — eskiden yalnızca non-thinking yol cache'liyordu,
  EXTENDED_THINKING açıkken her çağrı tam input token maliyeti ödüyordu.
- **Tüm analiz skill'leri RAG kullanır:** `surec_analizi`, `teknik_analiz`, `brd_analizi`, `kapsam_analizi`
  → `referans_dosyalari_hazirla()` + `_ref_bloklari_olustur()`.

## Sistem Promptları (18) — `VARSAYILAN_PROMPTLAR` (`skills/base.py`)
Tutarlı yapı: `# ROL → GÖREV → ÇIKTININ AMACI → ÇALIŞMA YÖNTEMİ → RAG İLKESİ → BAĞLAM KULLANIMI → KALİTE ÖLÇÜTÜ`.
```
surec_analizi_rol   surec_analizi          teknik_analiz_rol   teknik_analiz_bolumler
teknik_analiz_sorular  teknik_analiz_denetci   brd_analizi_rol   brd_analizi_bolumler
brd_analizi_sorular   kapsam_analizi_rol   kapsam_analizi_bolumler   kapsam_analizi_alternatifler
html_mockup_base   jira_tasks   refine   confluence_publisher   test_senaryolari   delta_analizi
```
- `teknik_analiz_denetci` (Aşama 3 denetçi): `_ORTAK_EK_KURALLAR` ALMAZ; sadece sorun tespit eder.
  UI prompt editöründe `_PROMPT_GRUPLARI` (index.html) "Süreç / Teknik Analiz" grubunda.
- **EK KURALLAR (otomatik append):** `prompt_yukle()` şu 5 prompta `_ORTAK_EK_KURALLAR` ekler:
  `surec_analizi`, `teknik_analiz_bolumler`, `kapsam_analizi_bolumler`, `brd_analizi_bolumler`,
  `jira_tasks` (`_EK_KURAL_SKILL_IDS`). `_ORTAK_EK_KURALLAR` 4 bölüm: Kaynak Önceliği, Kaynak İzleme
  `[K: ...]`, Halüsinasyon Koruması (Entity Whitelist), İzlenebilirlik (aşama bazlı ID tablosu).
- **Override:** `reference/prompts.json` (UI'dan düzenlenince); `prompt_yukle()` önce override, yoksa varsayılan.
- **Özel Prompt (analiz-bazlı, EN YÜKSEK öncelik):** Süreç/Teknik Analiz ekranındaki "Özel Prompt"
  paneli (`op-surec`/`op-teknik` textarea'ları) → `context_filter.json → ozel_prompt.{surec,teknik}`.
  Dolu alan, ilgili analizde varsayılan promptun (rol + bölümler + `_ORTAK_EK_KURALLAR`) **tamamen
  yerine geçer** (`ozel_prompt_oku()`, `skills/base.py`).
  **Miras kuralı (`teknik_ozel_prompt_oku()`):** teknik alan boşsa SÜREÇ özel promptu teknik
  analize de taşınır — analist tek prompt girdiğinde tüm pipeline onu baz alır, teknik aşama
  sessizce varsayılana dönmez. İki alan da boşsa mevcut zincir aynen çalışır.
  Teknik analizde `<teknik_analiz>` XML çıktı zorunluluğu özel prompta OTOMATİK eklenir — pipeline
  (`_xml_ayir`, kesik-çıktı retry'ı) bu bloğa bağımlı, analist bunu bilmek zorunda değil.
  **Kaydetme — ÜÇ başlatma yolu da ekrandaki değeri kaydeder:** `runPipeline` (Başlat),
  `sadeceTeknikBaslat` (Sadece Teknik Analiz) ve `onayla` (Devam Et — Teknik Analiz Başlat) önce
  `buildContextFilter()`'ı POST'lar. (Geçmiş bug: son ikisi kaydetmiyordu → analist promptu yazıp
  bu yollardan başlatınca alt süreç eski/boş değeri okuyup VARSAYILAN prompta düşüyordu —
  "özel prompt çalışmıyor" algısının kaynağı.)
  **Doğruluk çekirdeği (`OZEL_PROMPT_DOGRULUK_EKI`, base.py):** Özel prompt varsayılan rol/bölüm
  promptlarının yerine geçer ama bu kompakt ek HER ZAMAN eklenir: verilen bağlamı (referanslar,
  Jira task içerikleri, Confluence, Swagger, canlı gözlem) aktif kullan; UYDURMA YASAK; ekran ↔
  servis eşleştir; `[K: ...]` kaynak etiketi kullan. Referans blokları + canlı uygulama MCP görevi
  kullanıcı-mesajı bloklarında taşındığından özel prompttan BAĞIMSIZ olarak aynen gider.
  **Özel promptta şablon dayatması YOK:** teknik analizin kullanıcı-mesajındaki "BR/AC/PA ID'lerini
  MUTLAKA referans al" talimatı nötr girdi talimatına döner; AI denetçi (varsayılan 11-bölümlük
  şablona göre denetler → yanlış bulgu üretirdi) atlanır ve denetim bölümüne not yazılır.
  Deterministik `surec_id_kapsam` çalışmaya devam eder (ID yoksa skor 1.0 — zarar vermez).

## ID Şeması (aşamalar arası izlenebilirlik)
```
BRD Analizi   : FR-XXX NFR-XXX US-XXX AC-XXX I-XXX
Süreç Analizi : A-XXX PA-XXX BR-XXX AF-XXX EF-XXX AC-XXX EK-XXX (ekran)
Teknik Analiz : T-FE-XX T-BE-XX  (Bölüm 2/5/7'den çıkarılan FE/BE görevleri)
Kapsam Analizi: YE-XXX (yeni) KL-XXX (kaldırılan) DG-XXX (değiştirilen)
```

## FE / BE Katman Ayrımı
Süreç adımları, iş kuralları, ekranlar ve teknik iş öğeleri **katman etiketi** taşır: `FE / BE / FE+BE /
Tek tip`. FE+BE Jira görevlerinin ayrı ama ilişkili açılmasını sağlar.
- Teknik analizde: Bölüm 7 → Frontend İş Kırılımı; Bölüm 2 (İş Gereksinimleri)+5 (API) → BE/işlevsel
  görevler (Jira hiyerarşisi buradan çıkar). Jira önizleme modalı her Story/Subtask'ta FE/BE rozeti gösterir.

## Teknik Analiz ÜÇ AŞAMALI (`teknik_analiz_yap` → tuple(teknik_yol, sorular_yol))
1. **Aşama 1:** teknik analiz 1-11. bölüm (Amaç/Hedefler, İş Gereksinimleri, Teknik Gereksinimler,
   Veritabanı, API, İş Mantığı, Frontend İş Kırılımı, Role Management, Hata Yönetimi, Teknik Borç,
   Kabul Kriterleri). 12. bölüm "Karar Bekleyen Konular" regex'le prompttan çıkarılır → `teknik-analiz.md`
   (ham) BİTER BİTMEZ kaydedilir.
2. **Aşama 3 (denetim):** `surec_id_kapsam()` deterministik — süreç ID'leri (BR/AC/PA/EF/EK) teknik analizde
   referans edilmiş mi. Ardından `_teknik_denetle()` (prompt `teknik_analiz_denetci`) AI denetçi: kaynaksız
   iddia, §5↔§7 validasyon drift'i, uydurma endpoint/tablo, hata tutarsızlığı. Kapsam özeti + bulgular
   `## 🔍 Otomatik Denetim Notları` olarak teknik-analiz.md SONUNA eklenir (try/except — denetçi çökerse ham korunur).
   **`HIZLI_MOD=true` (.env) → AI denetçi ATLANIR** (`hizli_mod_acik()`, base.py): denetçi, teknik+süreç
   metninin tamamını İKİNCİ kez gönderen en pahalı ikinci çağrıdır — 429 limitine takılan ekipler için
   token tasarrufu. Deterministik kapsam denetimi her durumda çalışır; denetim bölümüne atlandı notu yazılır.
3. **Aşama 2:** ayrı `_api_cagri` — ham Aşama 1 + süreç analizi → açık sorular → `acik-sorular.md`
   (`### Q-T-NNN:` blok). Kapsamda karşılanmayan ID'ler Aşama 2'ye verilip GARANTİLİ soruya dönüşür.
- **Boş bölüm kuralı:** kapsam yoksa bölüm uydurulmaz; başlık + tek satır not.
- **Kesilme koruması:** `_teknik_uret_tam()` Aşama 1 yanıtında kapanış `</teknik_analiz>` yoksa kesilmiş
  sayar, yeniden dener (max 2, retry'da önbellek bypass); başaramazsa en dolu çıktıyı kaydedip uyarır.
  `_xml_ayir` kapanış etiketi yoksa yarımı stray-etiketsiz kurtarır.

## Mimari: subprocess + `sys.stdin.isatty()`
```
Tarayıcı → fetch /api/run → app.py → subprocess.Popen(run.py {mod})
                                  ↓  run.py → skills/* → Claude API
app.py /api/workflow-state ← polling 1.5s, workflow.py durum okur
not sys.stdin.isatty() → GUI modu (input() çağrılmaz, otomatik onay)
```
- Subprocess: `encoding="utf-8", errors="replace", start_new_session=True`; `_bekle()` thread'i
  timeout/crash'i yakalar, workflow'u HATA'ya çeker; zip-bomb koruması (compression ratio >100 atla).
- **Timeout katmanları** (CLI tam çıktıda yavaş): `_api_cagri_cli`/API SDK = 1200s (20 dk);
  app.py `_bekle` subprocess = 1320s (22 dk, CLI'dan FAZLA ki claude timeout'u önce tetiklensin).
- **CLI `--output-format json`** (text DEĞİL): text uzun/çok-turn yanıtta çıktının başını kaybediyordu;
  json `result` tam döner, `stop_reason`/`is_error` ile kesilme tespiti. `_claude_yolu_bul()` PATH'e
  bağımlı değil (GUI minimal PATH için nvm/~.local/homebrew tarar).

## Jira Görevleri Özelliği (`skills/jira_gorevleri.py` + UI `page-jira-gorevler`)
Doküman yüklemeden, **mevcut** Jira Epic/Story altındaki görevleri çekip triyaj eder.
- **Çekme:** `alt_gorevleri_cek` üç bağ modelini birleştirir (tekrarsız): `parent = KEY` (sub-task),
  `"Epic Link" = KEY` (epic), `issue in linkedIssues(KEY)` (Relates — bazı ekipler hiyerarşi yerine kullanır).
  Görev yorumları (ADF→metin) da çekilir. `parent_key` JQL'e girmeden `_ID_DESENI` ile doğrulanır (enjeksiyon engeli).
- **İki fazlı sınıflandırma:** FAZ 1 (`/cek`, `ai_kullan=False`) yapısal ön-tarama (`_yapisal_skor`),
  anında 0 token, `kaynak=yapisal`. FAZ 2 (`/siniflandir`, "AI ile Sınıflandır") AI her görevi içerikten
  okur (parçalı), `kaynak=ai`, opt-in.
- **Benzer içerik:** `benzer_gorevleri_isaretle` Jaccard (eşik 0.35, 0 token) → kartta sarı uyarı + link.
- **İki aksiyon:** *Hızlı İşleme Alınacak* → **Standart Formatla** (4 başlık, Haiku); *Detaylı Analiz
  Gerekir* → **Teknik Analiz Et** (Sonnet teknik analiz [RAG + bağlam filtresi dahil] + ayrı Haiku açık-sorular;
  modal'da 2. sekme, Jira'ya yazılmaz).
- **UI:** arama/filtre, katlanabilir gruplar, tam ekran modal (`.jg-modal`, Esc), `_jgTabAktif` üst-bar guard.
  **Onayla** → `gorev_jiraya_yaz` Jira description'ı ÜZERİNE YAZAR (atlassian_put + markdown_to_adf; HTML yorumları silinir).

Soru Defteri durumları: `acik / bekleniyor / cevaplandi / atlandi / varsayim` (kalıcı `output/sorular.json`, atomik).

## Canlı Uygulama (Chrome MCP) — ekran + servis gözlemi
Bağlam filtresinde `live_app.target_url` (+ en fazla 5 `extra_urls`) doluysa süreç/teknik analiz
sırasında `claude -p` alt süreci gerçek uygulamayı gezip DOM + network (BFF) gözlemi toplar.

**KRİTİK — izin/araç zinciri (`skills/base.py`):**
- `_live_app_cli_argumanlari(kapsam: str|None)` **OPT-IN**'dir: yalnızca çağıran, mesajlarına
  GERÇEKTEN bir browsing talimatı (`canli_uygulama_baglami_hazirla()` çıktısı) eklediyse
  `kapsam="surec"` veya `kapsam="gorev"` verir ve o zaman şu argümanlar eklenir:
  `--mcp-config .mcp.live-app.json --strict-mcp-config --allowedTools <15 tarayıcı aracı>`.
  `kapsam=None` (varsayılan) → canlı uygulama HİÇ açılmaz, global URL tanımlı olsa bile.
- **Geçmiş bug (düzeltildi):** Eskiden bu kontrol yalnızca "global URL tanımlı mı" bakıyordu —
  browsing talimatı içermeyen HER `_api_cagri()` çağrısı (BRD analizi, kapsam analizi, HTML
  mockup, Jira görev sınıflandırma/"Standart Formatla", teknik analizin denetçi + açık-sorular
  aşamaları) de gereksiz yere Playwright MCP başlatıyordu — talimat olmadığı için tarayıcı hiç
  kullanılmıyordu ama her çağrı dakikalarca npx/Chrome başlatma yüküne katlanıyordu (bir teknik
  analiz koşusunda "🌐 Canlı uygulama modu" 3 kez basılıyordu, oysa yalnızca 1. aşama browsing
  talimatı içeriyordu). `canli_uygulama_kapsami` parametresi artık yalnızca gerçekten talimat
  içeren çağrılarda ("surec": `surec_analizi.yap`, `teknik_analiz`'in 1. aşaması;
  "gorev": `gorev_analiz_et`) veriliyor; diğer tüm çağrılar hiç geçmiyor → varsayılan olarak kapalı.
- `--allowedTools` VERİLMEZSE headless `-p` modunda izin sorulamaz → tarayıcı araçları
  **sessizce reddedilir** (`permission_denials`) ve özellik çalışmaz. Eski hata buydu.
- `live_app_mcp_config_yaz()` MUTLAK yollarla config üretir: `npx -y @playwright/mcp@latest
  --headless --browser chrome --user-data-dir .live-app-profile`.
- `_npx_yolu_bul()` PATH'e bağımlı değil (GUI minimal PATH); npx'in dizini `cli_env["PATH"]`e eklenir.
- `LIVE_APP_ALLOWED_TOOLS`: navigate/navigate_back/snapshot/**network_requests + network_request**/
  console/click/type/press_key/hover/select_option/wait_for/handle_dialog/tabs/find.
  `browser_evaluate` (keyfi JS), `browser_file_upload`, cookie/localStorage/sessionStorage
  okuma-yazma, `browser_run_code_unsafe`, mouse-seviyesi kontrol, route interception, video/tracing
  bilinçli olarak DIŞARIDA (paket 0.0.78'de bunlar dahil ~65 araç var; yalnızca gözlem için
  gereken salt-okunur/dar kapsamlı 15 tanesi allowlist'te).
- **Geçmiş bug (düzeltildi):** `browser_network_requests` (çoğul — numaralı liste döner) ile
  `browser_network_request` (tekil — listedeki bir isteğin tam header/body detayını döner) PAKETTE
  İKİ AYRI ARAÇ; eskiden yalnızca çoğul olan listede vardı. Model detay için tekili çağırınca
  headless `-p` modunda onay alamıyor, `permission_denials`'a bile düşmeden "Analist onayı
  bekleniyor" durumunda süresiz askıda kalıyordu (kullanıcı raporu: UI'da onaylayacak bir
  modal/alan da yok — headless modda zaten hiç olamaz). Artık ikisi de allowlist'te.

**Oturum/login:** `.live-app-profile/` kalıcı Chrome profili (gitignored, çerez içerir).
`POST /api/live-app/login` sistem Chrome'unu bu profille HEADED açar → analist bir kez giriş yapar,
pencereyi kapatır (profil kilidi). Sonraki headless analizler aynı çerezleri kullanır.
`GET /api/live-app/status` → `{npx, urls, profil, hazir}`; UI'da Bağlam Filtresi altında durum
noktası + "Tarayıcıda Giriş Yap" butonu. `live_app_profil_var_mi()` profil hazırlığını gösterir,
**giriş yapıldığını KANITLAMAZ** — analiz login sayfasına düşerse prompt kuralı gereği varsayım
üretmeden bildirir.

**Kapalıyken:** live_app URL'i yoksa hiçbir ek argüman geçmez → normal analiz davranışı aynen korunur.

**Sistematik tarama planı (`canli_uygulama_baglami_hazirla`):** MCP görevi serbest "gez ve gözle"
değil, zorunlu sıralı bir plandır: (1) açılış snapshot + network, (2) TÜM tablar/segment kontrolleri
(`?tab=` yalnızca başlangıç), (3) her aksiyon butonunun modal/formu — alan tipi/zorunluluk/default/
cascade, (4) filtre/arama/sayfalama + query parametreleri, (5) CRUD (aşağıdaki kurallara göre GERÇEK),
(6) her aksiyondan sonra `browser_network_requests`, kritik isteklerin detayı `browser_network_request`,
(7) edge-case'ler (boş liste/loading/hata/yetki). Gözlemler "adım → beklenen/gözlenen sonuç" (test
senaryosu türetilebilir) formatında; çıktı sonuna **"Canlı Gözlem Kapsamı" raporu zorunlu** (gezilen +
YAPILAN yazma işlemleri + gezilemeyen ve nedeni). NOT: derin tarama uzun sürer — CLI timeout 20 dk;
alt URL sayısını sınırlı tut, gerekirse HIZLI_MOD ile denetçi aşamasından süre kazan.

**CRUD kuralları (test ortamı — yazma GERÇEKTEN uygulanır):** Test ortamı linkleri verildiği için
create/update uçtan uca yapılır ve yazma servislerinin gerçek istek/yanıt çiftleri (method, path,
payload, status, gövde özeti) yakalanır — bug-fix/CR analizlerinin dayanağı budur. Koruma sınırları:
oluşturulan kayıtlara `AI-TEST` öneki; SİLME yalnızca bu oturumda kendi oluşturduğu kayıtlarda;
GERİ ALINAMAZ süreç aksiyonları (ödeme, rollback, publish, onaya gönderme) UYGULANMAZ —
`[K: 🔍 Türetilmiş]` + açık soru. Yapılan tüm yazmalar Gözlem Kapsamı raporunda listelenir.

**Odaklı gözlem (`gozlem_kapsami`):** `live_app.gozlem_kapsami` / `live_app_gorev.gozlem_kapsami`
(her ekran KENDİ alanını kullanır) doluysa tam tarama planı YERİNE analistin tarif ettiği bölüm/akış
uçtan uca ve derinlemesine incelenir ("ekranın tamamını taramak zorunda değilsin" + validasyon/hata
edge-case'leri dahil) — daha hızlı, daha az token, bug-fix/CR hedefine isabetli. UI: Bağlam
Filtresi'nde "MCP Gözlem Kapsamı" textarea'sı (`ctx-live-scope`), Jira Görevleri widget'ında
`jg-live-scope`. CRUD kuralları ve kayıt formatı iki modda da ortaktır. Belirli bir akışı hedeflemek
için doğru araç BUDUR — Özel Prompt değil (o sistem promptunu değiştirir, gezinme görevine dokunmaz).

**Özel Prompt ile ilişki:** MCP görevi SİSTEM promptunda değil, kullanıcı mesajı bloğunda
(`stable_bloklar`) taşınır — ekrandaki Özel Prompt varsayılan sistem promptunun yerine geçse bile
canlı uygulama görevi + araç izinleri AYNEN gider; gözlem etiket kuralları görev bloğunun içinde
olduğundan özel promptta tekrar yazılması gerekmez.

**Jira Görevleri'nden erişim — BAĞIMSIZ ikinci hedef (`live_app_gorev`):** Süreç/Teknik Analiz'in
`live_app` alanından TAMAMEN ayrı, `context_filter.json`'da ikinci bir alan: `live_app_gorev`
(yalnızca `target_url`; alt URL/örnek-ekran kavramı yok — task bazlı tek ekran içindir). İki akış
birbirinin URL'ini asla kullanmaz:
- `gorev_live_app_urls()` / `live_app_urls()` (`skills/base.py`) ayrı okuma fonksiyonları.
- `canli_uygulama_baglami_hazirla(gorev: bool)` hangi hedeften talimat metni üretileceğini seçer;
  `_api_cagri(..., canli_uygulama_kapsami="gorev")` yalnızca `gorev_analiz_et()`
  (`skills/jira_gorevleri.py`) bu talimatı gerçekten ürettiğinde verilir. `_gorev_acik_sorular_uret()`
  (Aşama 2, zaten üretilmiş metni özetler) hiçbir kapsam GEÇMEZ — browsing talimatı içermediği için
  canlı uygulama hiç açılmaz (bkz. yukarıdaki "Geçmiş bug" notu).
- UI: Jira Görevleri sayfasında ("Üst Görev" paneli) Bağlam Filtresi'yle aynı `.la-durum` bileşenini
  (`jg-live-target`/`jg-la-*` id'leriyle) kullanan ayrı bir widget. `jgLiveAppKaydet()` mevcut filtreyi
  GET edip `live_app`'e DOKUNMADAN yalnızca `live_app_gorev.target_url`'i güncelleyip geri POST'lar
  (`/api/context-filter` POST'u tam nesne bekler — kısmi gönderim diğer alanları silerdi).
  `jgLiveAppGiris()` alan boşsa backend'in `live_app_urls()` fallback'ine (Süreç'in URL'i) düşmesin
  diye istemci tarafında erken çıkar.
- `GET /api/live-app/status?scope=gorev` → `gorev_live_app_urls()`; parametresiz → Süreç'in `live_app`'i.
  Profil/npx durumu ortak (aynı `.live-app-profile` Chrome oturumu paylaşılır), yalnızca `urls`/`hedef` ayrışır.

**Profil kilidi self-heal:** Chrome aynı `--user-data-dir`'i tek seferde yalnızca bir süreçte açabilir.
Analist HEADED giriş penceresini kapatmayı unutursa hem yeni "Tarayıcıda Giriş Yap" tıklaması hem de
analiz sırasındaki headless Playwright başlatması aynı kilide takılır (`claude -p` non-interactive
çalıştığından, kilidi tutan yetim süreç bir insan/agent onayı olmadan sonlandırılamaz → analiz askıda
kalır). `live_app_kilidi_temizle()` (`skills/base.py`) bunu otomatik çözer: `SingletonLock`
symlink'inden PID'i okur, süreç yaşıyorsa SIGTERM gönderip **en fazla ~5 sn** (0.25 sn aralıklarla
poll) kendiliğinden kapanmasını bekler, hâlâ yaşıyorsa SIGKILL'e düşer; `Singleton*` dosyalarını
siler. Hem `POST /api/live-app/login`'de (her tıklama gerçekten temiz pencere açsın) hem
`_live_app_cli_argumanlari()`'nde (her live-app'li analiz temiz başlasın) çağrılır — ayrı bir onay
akışı gerektirmez, uygulama kendi kaynağını kendi temizler.

**Neden 5 sn poll (sabit 1 sn değil):** Chrome SIGTERM'i normal kapanış sayar ve bu sırada
çerezleri/oturum verisini diske yazar (flush) — ama bu anlık değil. İlk sürümde sabit 1 sn bekleyip
koşulsuz SIGKILL atılıyordu; analist TAM O SIRADA giriş yapıp pencereyi henüz kapatmışsa (veya
analiz otomatik başlayıp self-heal'i tetiklemişse) taze çerezler flush olmadan kesilme riski vardı —
sonuç: profil "hazır" görünür ama analiz yine login duvarına düşer (giriş yapılmış gibi görünüp
aslında geçerli oturum kaydedilmemiş olur). Artık süreç kendiliğinden kapanana kadar bekleniyor,
yalnızca gerçekten yanıt vermiyorsa zorla kapatılıyor.

**Otomatik giriş (opsiyonel):** Bağlam Filtresi panelinde (Süreç ekranı) `live_app_auth`
(kullanıcı adı + şifre) girilirse, MCP tarayıcısı bir login/giriş formuna düşünce bu bilgilerle
otomatik giriş yapıp devam eder — önceden yalnızca "login duvarına takıldı" diye açık soru
üretilebiliyordu. `live_app_auth` **iki akış da (Süreç/Teknik Analiz + Jira Görevleri) paylaşır**
(aynı test hesabı); `canli_uygulama_baglami_hazirla()` her iki `gorev` değeri için de bu bilgiyi
ekler. Şifre `reference/context_filter.json`'da düz metin tutulur — dosya zaten gitignore'da
(hard kural #2) ve `context_filter_kaydet()` yazımdan sonra dosya iznini 600'e sıkılaştırır.
Prompt talimatı modele şifreyi ASLA çıktıya yazmamasını söyler (mevcut token/cookie maskeleme
kuralına ek).

**`/api/context-filter` POST artık PATCH semantiği kullanır (düzeltildi):** Eskiden istek
gövdesinde eksik olan HER üst-düzey alan boş değere sıfırlanıyordu — bu yüzden Süreç ekranından
kaydedince (`buildContextFilter()` `live_app_gorev` alanını hiç bilmez) Jira Görevleri'nin hedefi
sessizce siliniyordu, ve tersi de geçerliydi. `context_filter_kaydet()` (`app.py`) artık önce
mevcut dosyayı okur; istek gövdesinde bulunmayan alan (`"anahtar" in data` değilse) mevcut kayıtlı
değerini korur. Yalnızca gövdede AÇIKÇA gönderilen alan güncellenir/silinir — `ctxFilterTemizle()`
gibi "temizle" akışları hâlâ çalışır çünkü ilgili alanı açıkça boş gönderirler.

## Bilinen Kısıtlamalar
- CLI modu görsel (PNG/JPG) analiz EDEMEZ (text-only); görsel BRD için API modu gerekir.
- `markdown_to_adf` nested list'leri düzleştirir.
- History limiti 5 (sabit, `save_to_history()`). Tek input dosyası (çok yüklenirse ilk).
- Atlassian-only (Azure DevOps/GitHub Issues yok). macOS-only dağıtım. Tek aktif analiz (sunucu modunda).
