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
MAX_CHARS_REF_GLOBAL=140_000  # GETİRİM BÜTÇESİ: tüm tiplerin TOPLAM tavanı (.env; 0=sınırsız).
                              # _ref_bloklari_olustur tipleri sırayla doldurur, bütçe dolunca keser.

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

### Jira'ya YAZILMAYAN bölümler — analist bilgisi vs. geliştirici task'ı
Analiz çıktısında KALIP Jira description'ına GİTMEYEN iki bölüm var; ikisi de analistin
doğrulama/şeffaflık bilgisidir, gereksinim değildir. Her Jira yazma yolu ikisini de çıkarır
(`gorev_jiraya_yaz` + `jira_tasks` hiyerarşi üretimi):
1. **Yönetici Özeti** → `yonetici_ozetini_cikar()` (başlıktan ilk `---` ayırıcıya kadar).
2. **Canlı Gözlem Kapsamı** → `canli_gozlem_kapsamini_cikar()`. MCP gözleminde nereye bakıldığını
   (gezilen tablar/modallar, YAPILAN yazma işlemleri, gezilemeyenler + nedeni) raporlar.
   Yönetici Özeti'nden farkı: sabit `---` ile bitmez → bölüm sonu **başlık seviyesine göre**
   belirlenir (aynı ya da daha üst seviyedeki sonraki başlık; yoksa doküman sonu). Başlıktaki
   emoji ve diakritiksiz yazım ("Canli Gozlem Kapsami") da yakalanır; bölüm silinince sarkan
   `---` ayırıcı da temizlenir. Modal önizlemede analist bölümü GÖRÜR (yalnızca yazılan kopya temizlenir).

## RAG Mimarisi (`skills/base.py`)
- **Bağlam blokları:** `_ref_bloklari_olustur(ref_dosyalar)` tipine göre gruplar — `### CONFLUENCE
  DOKÜMANTASYONU` (md), `### JİRA TASK GEÇMİŞİ` (`_jira_json_to_md` kompakt md), `### API / SWAGGER
  TANIMLARI` (filtrelenmiş openapi), `### CANLI UYGULAMA GÖZLEMİ` (`reference/live-app`),
  `### DİĞER REFERANSLAR`. Her tip ayrı limitle.
- **PDF-farkında filtre + keyword-odaklı çıkarım (KRİTİK):** `filtrele_referanslar` içerik-eşleşmesini
  `_filtre_metni_oku` (PDF'i `pdf_oku`/fitz ile çıkarır) üzerinden yapar — düz `read_text` bir PDF'i binary
  çöp okuyup ilgili referansı YANLIŞLIKLA elerdi (ör. 6.7 MB `TradePanel_1_7_9.pdf` confluence referansı).
  Confluence filtresi dosya adı VEYA içerik eşleşmesiyle dahil eder (farklı adlı ilgili sayfa da gelir).
  RAG blok üretiminde büyük dosya limitten (MAX_CHARS_REF=15K) büyükse `_keyword_odakli_metin` baştan
  kesmek yerine keyword geçen yerlerin ETRAFINDAN pencereler alır → ilgili bölüm (ör. Publish Overview
  PDF'in %25'inde) 15K bütçeye girer. Keyword yoksa baştan-kesmeye döner.
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
  **Görev analizinde 2. breakpoint (madde 3):** görev içeriği (key/başlık/açıklama + analist notu) cevap/düzeltme
  turları arasında değişmez → refs breakpoint'ine ek olarak görev bloğuna da konur; cevap turlarında görev
  içeriği cache'ten okunur (sistem+refs+görev = 3 breakpoint, tavan 4). CLI modu cache_control yok sayar.
  THINKING yolunda da aktif (`_api_cagri_direct`) — eskiden yalnızca non-thinking yol cache'liyordu,
  EXTENDED_THINKING açıkken her çağrı tam input token maliyeti ödüyordu.
- **Tüm analiz skill'leri RAG kullanır:** `surec_analizi`, `teknik_analiz`, `brd_analizi`, `kapsam_analizi`
  → `referans_dosyalari_hazirla()` + `_ref_bloklari_olustur()`.

## Sistem Promptları (19) — `VARSAYILAN_PROMPTLAR` (`skills/base.py`)
Tutarlı yapı: `# ROL → GÖREV → ÇIKTININ AMACI → ÇALIŞMA YÖNTEMİ → RAG İLKESİ → BAĞLAM KULLANIMI → KALİTE ÖLÇÜTÜ`.
```
surec_analizi_rol   surec_analizi          teknik_analiz_rol   teknik_analiz_bolumler
teknik_analiz_sorular  teknik_analiz_denetci   brd_analizi_rol   brd_analizi_bolumler
brd_analizi_sorular   kapsam_analizi_rol   kapsam_analizi_bolumler   kapsam_analizi_alternatifler
html_mockup_base   jira_tasks   refine   confluence_publisher
gorev_teknik_analiz   test_senaryolari   delta_analizi
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

## Süreç Analizi Çıktı Formatı (analiz ekibi Confluence şablonu)
`VARSAYILAN_PROMPTLAR["surec_analizi"]` çıktısı, analiz ekibinin Confluence sayfalarıyla **aynı iskeleti**
üretir: üstte metadata tablosu (Target Release/Epic/Story/Jira Task/Jira Subtask/Analyst/Ürün Doküman
Versiyonu — değerler BOŞ; analist Confluence'a taşırken doldurur) → **AMAÇ → MOCKUP → GEREKSİNİMLER**
(İş Gereksinimleri↔İş Kuralları tablosu + Aktörler + numaralı **Ekranlar**: her ekran `Alan Adı | Açıklama`
ve `Buton Adı | Açıklama` tabloları + **Süreç Adımları** iş akışı) → **ÖNERİLEN DB ALANLARI → GELİŞTİRME
NOTLARI** (Sistemler ve Entegrasyonlar, Kabul Kriterleri, Karar Tabloları, Açık Sorular).
GEREKSİNİMLER altında **İlişkili Ekranlar / Süreçler ve Etki Analizi** (IB-XXX) bölümü zorunlu: referanslardan
bu süreçle ilişkili/etkilenen ekran-süreçleri, paylaşılan bileşen/servis/kural/entity'yi ve değişikliğin
etkilerini çıkarır (izole varsayma). Prompt'ta **KAYNAK KULLANIMI (ZORUNLU)** bloğu: sağlanan tüm
referansları (Confluence/Jira board/Swagger/canlı uygulama) aktif kullan, yüzeysel/tek-kaynaklı analiz üretme.
**Pipeline korunur (B yaklaşımı):** ID'ler (A/BR/PA/AF/EF/EK/AC/Q) ilgili bölümlere gömülür →
`surec_id_kapsam` + RTM çalışır; `### Süreç Adımları` başlığı mermaid enjeksiyonunun çapası;
`| Q-001 | …` tablosu Soru Defteri (`sorular._TABLO_SORU_SATIR`) çapasıdır. Format değişikliği bu üç
çapayı bozmamalıdır.

## HTML Prototip — canlı uygulama baz'lı (`skills/html_mockup.py`)
`html_mockup_uret()` süreç analizinden `mockup.html` üretir. **Canlı uygulama baz'ı:** context_filter
`live_app` (target_url + extra_urls) doluysa `canli_uygulama_baglami_hazirla()` ile Chrome MCP gezinme
görevi kurulur ve `_api_cagri(..., canli_uygulama_kapsami="surec")` ile CLI modunda **Playwright MCP açılır**;
`claude -p` verilen ekran(lar)ı gezip tasarım sistemini (palet/tipografi/spacing) + component desenlerini
(sidebar/tablo/form/buton/modal/tab/chip) çıkarır ve prototip bunlara birebir uyar. İçerik kaynağı süreç
analizinin **GEREKSİNİMLER → Ekranlar** (EK-XXX, Alan/Buton tabloları) bölümüdür. Tüm component'ler çalışır
(nav geçiş, form submit+doğrulama, tablo mock veri, modal aç/kapa). URL yoksa generic tasarım ipucuna düşer
(fallback korunur). `html_mockup_base` promptu buna göre güncellendi (eski "Bölüm 9" referansı yeni formata taşındı).

## ID Şeması (aşamalar arası izlenebilirlik)
```
BRD Analizi   : FR-XXX NFR-XXX US-XXX AC-XXX I-XXX
Süreç Analizi : A-XXX PA-XXX BR-XXX AF-XXX EF-XXX AC-XXX EK-XXX (ekran) IB-XXX (ilişki/etki)
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
- **Timeout katmanları** (CLI tam çıktıda yavaş): `_api_cagri_cli`/API SDK = 1200s (20 dk) **her claude
  çağrısı başına**; app.py `_bekle` subprocess = **MOD-BAZLI**: `teknik_analiz`/`brd_analizi` ÇOK AŞAMALIDIR
  (Aşama 1 teknik + canlı-uygulama MCP gezinme, Aşama 2 açık sorular = 2 ayrı çağrı, +olası Aşama 1 retry)
  → **2700s (45 dk)**; tek-çağrılık modlar (surec_analizi, kapsam_analizi, jira_gonder) → **1800s (30 dk)**.
  Eski sabit 1320s tek çağrıya göreydi → teknik analizde 2. aşama başlarken yanlışlıkla öldürüp "22 dk
  zaman aşımı" veriyordu. Dış timeout çağrı DİZİSİNİ kapsar; iç 1200s tek çağrının asılı kalmasını engeller.
- **CLI `--output-format json`** (text DEĞİL): text uzun/çok-turn yanıtta çıktının başını kaybediyordu;
  json `result` tam döner, `stop_reason`/`is_error` ile kesilme tespiti. `_claude_yolu_bul()` PATH'e
  bağımlı değil (GUI minimal PATH için nvm/~.local/homebrew tarar).

## UAT Mutabakat (ekran adı; `skills/backlog_senkron.py` + UI `page-backlog-senkron`)
Product'ın **UAT board'unda** (MBSUATEAM) açtığı taskları bizim **TRADE/OPS board**
(MBSTRADE/MBSOPS) tasklarıyla karşılaştırır; hangi UAT maddesinin işleme alınmadığını (açıkta
kalan iş) ve hangi hedef taskın kaynağının UAT'de bulunmadığını ortaya çıkarır. Analist tek tıkla
çalıştırır, sonucu ekranda görür, çok sayfalı Excel raporu indirir. **Excel girişi YOK** (eski
takip-Excel senkron akışı — upload + cerrahi lxml yazımı — bu sürümde kaldırıldı).
- **0 LLM tokenı — tamamen deterministik.** `claude -p`/MCP ÇAĞRILMAZ; yalnızca Jira REST okuması +
  openpyxl ile sıfırdan .xlsx yazımı (yeni dosya → cerrahi zip korumasına gerek yok).
- **İki board'u çek:** `mutabakat(uat_proje, hedef_projeler, mod, hedef_keys, anahtar_kelime)`. UAT
  board'u HER ZAMAN tam taranır (`project = UAT`). Hedef tarafı `mod`'a göre toplanır:
  `tum` (`project in (hedef...)`), `epic` (her key için `alt_gorevleri_cek` — parent+Epic Link+
  linkedIssues birleşimi; sonuç **hedef board'lara göre filtrelenir** = epic altındaki ama başka
  projedeki görevler elenir → tüm board yerine ilgili alt küme, token/zaman tasarrufu),
  `keyword` (`project in (...) AND text ~ "kelime"`). JQL literal'leri
  `_jql_kacis` ile kaçışlanır. Görevler `jira_gorevleri._issue_ayrıstir` ile ayrıştırılır (özet,
  durum, açıklama, **baglantililar** = issue-link listesi).
- **Katmanlı eşleştirme (güçlüden zayıfa):**
  1. **KESİN** — UAT ile hedef arasında zaten Jira issue-link var (iki yön de taranır, tekrarsız).
  2. **YÜKSEK** — link yok ama başlık+içerik Jaccard benzerliği `ESIK_YUKSEK` (0.55) üstünde →
     otomatik eşleşme. Jetonlar `jira_gorevleri._benzerlik_jetonlari` (başlık + açıklama ilk 300).
  3. **ADAY** — Jaccard `ESIK_ORTA` (0.35) ile `ESIK_YUKSEK` arası → analist teyit eder.
  4. **EŞLEŞMEYEN** — UAT tarafı (açıkta kalan iş) VE hedef tarafı (kaynağı UAT'de olmayan) ayrı ayrı.
  Dönüş: `eslesenler`, `adaylar`, `eslesmeyen_uat`, `eslesmeyen_hedef`, `sayimlar`, `jira_url`.
- **`jira_url` (browse link'leri için):** canonical `atlassian.jira_site_url()` accessible-resources
  endpoint'inden cloud_id eşleşmesiyle site adresini (ör. `https://firma.atlassian.net`) alır, süreç
  boyunca cache'ler. **`.env` `JIRA_URL`'e GÜVENMEZ** — o bazı kurulumlarda OAuth callback adresini tutuyor;
  yalnızca `.atlassian.net` içeriyorsa yedek olarak kullanılır. Aynı helper `jira_agent.py` task-oluşturma
  browse link'lerinde de kullanılır (tek kaynak).
- **Sıralama:** tüm kovalar UAT sıra no'suna (`_sira_no` = key sonundaki sayı, MBSUATEAM-116→116; hedef
  kovası kendi key no'suna) göre ARTAN sıralanır → karışık liste değil 1,2,3… Her satırda `sira` alanı;
  UI ve export'ta ilk kolon "Sıra".
- **Export (`rapor_uret`):** openpyxl `Workbook` ile sıfırdan 3 sayfa: `Eşleşenler` (Sıra + eşleşen+aday,
  **Eşleşme** (Evet/Aday) + Gerekçe kolonlu), `Eşleşmeyen UAT`, `Eşleşmeyen TRADE-OPS` (hepsi Sıra kolonlu).
  Başlık dolgusu + freeze + autoFilter. UI'da (export'a yansımaz): stat kartları FİLTRE'dir (`bsFiltrele` —
  tıkla → yalnızca o grup görünür, aktif karta tekrar tıkla → tümü); satır rozetleri (✓ Eşleşti / ● Aday /
  ✕ Eşleşmedi); task key'leri Jira browse link'i (bold + ↗, yeni sekme); UAT durumu ≠ Hedef durumu olan
  satırlarda iki durum hücresi amber + "≠" ile vurgulanır (`bs-durum-fark`).
  Zaman damgalı `UAT_Mutabakat_YYYY-MM-DD_HHMM.xlsx`, `backlog/` altına.
- **Endpoint'ler:** `POST /api/backlog/mutabakat` (config → kova JSON) · `POST /api/backlog/export`
  (sonuç body → `{dosya}`) · `GET /api/backlog/indir/<dosya>` (binary `send_file`). Dosyalar `backlog/`
  altında (gitignore). Bağımlılık: `openpyxl` (requirements.txt).

## Jira Görevleri Özelliği (`skills/jira_gorevleri.py` + UI `page-jira-gorevler`)
Doküman yüklemeden, **mevcut** Jira Epic/Story altındaki görevleri çekip triyaj eder.
- **Çekme — İKİ AŞAMALI (keşif + taze okuma):**
  1. **Keşif (arama):** `alt_gorevleri_cek` üç bağ modelini birleştirir (tekrarsız):
     `parent = KEY` (sub-task), `"Epic Link" = KEY` (epic), `issue in linkedIssues(KEY)`
     (Relates — bazı ekipler hiyerarşi yerine kullanır). Bu aşama yalnızca HANGİ issue'ların
     bağlı olduğunu belirler. `parent_key` JQL'e girmeden `_ID_DESENI` ile doğrulanır (enjeksiyon engeli).
  2. **Taze içerik (`_taze_issue_oku` → `POST /rest/api/3/issue/bulkfetch`, 100'lük parçalar):**
     başlık/açıklama/yorum/bağlantılar DOĞRUDAN issue'dan okunur.
     **NEDEN:** `/rest/api/3/search/jql` sonuçları arama İNDEKSİNDEN gelir ve indeks
     eventually-consistent'tır — Atlassian dokümanı: *"Recent updates might not be immediately
     visible in the returned search results."* Bu yüzden Jira'da bir task'ın başlığı/açıklaması
     güncellendikten sonra görevler yeniden çekilse bile ESKİ içerik dönebiliyordu. bulkfetch
     indeksi atlar → güncellemeler anında görünür. bulkfetch başarısız olursa (yetki/endpoint)
     arama sonucuna düşülür — akış kırılmaz, yalnızca bayat olabilir.
  3. **Girilen anahtarın KENDİSİ (`_kapsayici_mi`):** Epic/Story ise *kapsayıcı* sayılır ve
     listede yer almaz (analist altındaki görevleri ister — eski davranış). Görev/Bug gibi
     *yaprak* iş kaleminde ise analistin asıl incelemek istediği şey odur → listenin EN ÜSTÜNE
     eklenir (kendisi + bağlı task'ları). **DİKKAT:** Jira'da Story ve Task AYNI
     `hierarchyLevel`'a (0) sahiptir — gerçek Jira'da doğrulandı (Hikaye=0, Görev=0) — bu yüzden
     ayrım tip ADIna göre yapılır (`_KAPSAYICI_TIP_ADLARI`: epic/epik/story/hikaye/initiative);
     `hierarchyLevel >= 1` her hâlükârda kapsayıcıdır (özel epic adlarını da kapsar).
  Ortak ayrıştırma `_issue_ayrıstir` (arama + bulkfetch aynı fonksiyonu kullanır): yorumlar
  (ADF→metin) ve `issuelinks` (`_issuelink_ayikla` → `baglantililar`: bağlı task key/summary/tip/
  ilişki + kaba `katman` tahmini be/fe/belirsiz `_katman_tahmin` ile).
- **İki fazlı sınıflandırma:** FAZ 1 (`/cek`, `ai_kullan=False`) yapısal ön-tarama (`_yapisal_skor`),
  anında 0 token, `kaynak=yapisal`. FAZ 2 (`/siniflandir`, "AI ile Sınıflandır") AI her görevi içerikten
  okur (parçalı), `kaynak=ai`, opt-in.
- **Sadece Client ayıklama** (`/gorevler/sadece-client`, "Sadece Client İşleri" butonu — opt-in): AI her
  görevi + BAĞLI task'larını inceleyip HİÇBİR BFF/BE değişikliği gerektirmeden yalnızca frontend'de
  tamamlanabilecekleri ayırır (`sadece_client_ayikla` → `{sadece_client, diger}`). Bağlı BE task'ı olan
  görev "sadece client" DEĞİLDİR (isterin sunucu tarafı ayrı task'ta geliştiriliyor). Emin olunamayan
  görevler güvenlik gereği `diger`e düşer (false-negatif, false-pozitiften güvenli). AI çağıramazsa
  (`_sadece_client_ai` boş dönerse) hiçbir görev "sadece client" KESİNLEŞTİRİLMEZ (fallback → hepsi `diger`).
  **PARÇALI TASARIM (çok görevde timeout/askıda kalma önlemi):** Endpoint tek batch alır
  (`{gorevler: [...]}`, en fazla `SADECE_CLIENT_BATCH_LIMIT=25`; Jira'dan yeniden çekmez, görevler
  client'tan gelir — `/formatla`, `/analiz` deseniyle aynı). Frontend tüm görevleri `SC_BATCH=20`'lik
  gruplara bölüp arka arkaya çağırır (`jgSadeceClient` döngüsü): her istek SINIRLI sürer (tek AI çağrısı),
  kısmi sonuçlar her grup sonrası birikip render edilir, ilerleme gösterilir (`n/toplam`), bir grup hata
  alsa öncekiler korunur. Buton çalışırken "Durdur"a döner (`_jgScDurdur` → mevcut grup bitince durur).
  **Eski tek-istek tasarımı KALDIRILDI** — 200+ görevde tek HTTP isteği dakikalarca sürüp tarayıcıda
  timeout olurken sunucu arka planda öğütmeye (token harcamaya) devam ediyordu.
  UI: mevcut iki grubu bozmadan 3. grup `#jg-sc-group` (varsayılan gizli, butonla üretilir); yeniden
  çekmede bayat sonuç gizlenir.
- **Tüm Görevler + statü filtresi (UI, `#jg-tum-group` — 0 token, tamamen frontend):** sonuç alanının
  EN ÜSTÜNDE, çekilen tüm görevleri listeleyen ana başlık. İçinde dinamik **statü filtre çubuğu**
  (`#jg-status-filtre`) — görevlerdeki distinct Jira statülerinden sayaçlı chip'ler (`Tümü` + her statü).
  **Çoklu seçim** (`_jgStatusSecili` Set; boş=tümü), `jgStatusToggle`/`jgTumFiltrele`. Statü filtresi
  YALNIZCA bu başlığı süzer; mevcut arama (`jgFiltrele`) ile birlikte çalışır. Kartlar ortak
  `_jgKartHtml(g, sinif)` ile çizilir (her görev `_grup` etiketiyle hazir/detay sol-kenar rengini korur).
  Export ('tum') aktif filtreye göre. Mevcut iki grup + Sadece Client + aksiyonlar aynen korunur.
  **Atanan kişi:** her kartta atanan rozeti (`assignee` displayName; boşsa italik `ATANMAMIŞ`) +
  filtre çubuğunda **dropdown** (`jg-assignee-select`: Tümü / her isim sayaçlı / ATANMAMIŞ).
  `_jgAssigneeSecili` (`''`=tümü, `JG_ATANMAMIS`=atanmamış, veya isim). Statü chip'leri + arama ile
  birlikte `_jgTumFiltreliListe()` üzerinden AND'lenir; yalnızca "Tüm Görevler"i süzer. `assignee`
  alanı Jira'dan zaten `_issue_ayrıstir` ile geliyor → 0 token, tamamen frontend.
- **Analist Notu (opsiyonel, `context_filter.json → gorev_analist_notu`):** Jira Görevleri ekranındaki
  textarea (`jg-analist-notu`, canlı-uygulamadan bağımsız; `jgAnalistNotuKaydet`/`jgAnalistNotuTemizle`,
  PATCH ile yalnızca kendi anahtarını yazar). Doluysa `gorev_analiz_et` bunu analiz kullanıcı-mesajına
  belirgin bir talimat bloğu olarak ekler ("mevcut promptla BİRLİKTE çalışır, doğruluk/spekülasyon
  kurallarını GEVŞETMEZ"). Boşsa hiç eklenmez (token yok). YALNIZCA "Teknik Analiz Et"i etkiler
  (Formatla/Sınıflandır/Sadece Client değişmez). Not: `_context_filter_normalize` (base.py) ve
  `context_filter_kaydet`/`_oku` (app.py) bu anahtarı açıkça taşır — sabit-şema rebuild'i düşürmesin diye.
- **İptal edilenler hariç:** görev çekiminde (`/cek` ve `/siniflandir`) `iptal_ayikla` iptal statülü
  görevleri listeden çıkarır (`_iptal_statusu_mu` — İptal Edildi / İPTAL EDİLDİ / Cancelled / Canceled;
  `upper()` ile, Türkçe İ casefold sorununu atlar). Bağlı task'lara dokunulmaz. Yanıt `iptal_haric`
  sayısını taşır; UI'da kalıcı bilgi notu ("İptal edilmiş biletler listeye dahil edilmemiştir" +
  varsa "N iptal edilen görev çıkarıldı", `#jg-iptal-not`).
- **Benzer içerik:** `benzer_gorevleri_isaretle` Jaccard (eşik 0.35, 0 token) → kartta sarı uyarı + link.
- **Triyaj KAPSAMI — yalnızca Backlog + atanmamış (`_triyaja_uygun_mu`):** *Hızlı İşleme Alınacak* ve
  *Detaylı Analiz Gerekir* gruplarına YALNIZCA durumu Backlog VE atanmamış görevler girer (analistin
  işleme alıp detaylandıracağı fresh işler). UAT/TAMAM/READY FOR TEST/Devam Ediyor gibi ilerlemiş
  görevler triyaja alınmaz. `gorevleri_siniflandir` üç liste döndürür: `hazir`/`detay` (triyaj alt
  kümesi) + `tum` (TÜM görevler). AI sınıflandırma yalnızca uygun görevlerde çalışır (token tasarrufu).
  UI: "Tüm Görevler" başlığı `tum`'u gösterir (triyaj dışı kartlar nötr — durum/gerekçe yok);
  Sadece Client de `tum` üzerinde çalışır; aksiyonlar tüm görevlerde geçerli.
- **İki aksiyon:** *Hızlı İşleme Alınacak* → **Standart Formatla** (4 başlık, Haiku); *Detaylı Analiz
  Gerekir* → **Teknik Analiz Et** (Sonnet + RAG/bağlam filtresi + ayrı Haiku açık-sorular; modal'da
  2. sekme, Jira'ya yazılmaz). Sadece-client görevlerinde de aynı iki aksiyon kullanılabilir.
  **YALIN PROMPT (`gorev_teknik_analiz`):** `gorev_analiz_et` artık ağır 11-bölümlük
  `teknik_analiz_bolumler` şablonunu KULLANMAZ (o, süreç→teknik ana pipeline'a özgüdür). Görev-bazlı
  analiz uyarlanabilir yalın bir prompt kullanır: yalnızca görevin GERÇEKTEN dokunduğu bölümler
  (Amaç/Kapsam · Etkilenen Alanlar · Teknik Değişiklikler · Kabul Kriterleri) kısa yazılır, ilgisiz
  başlıklar HİÇ açılmaz ('kapsam dışı' dolgu yok). Basit görev 2-3 kısa bölüm olur → sistem promptu
  ~16K→~2K krk (~%87 girdi tasarrufu) + çok daha kısa çıktı. Kalite güvenceleri korunur (kaynak
  etiketleri `[K:...]`, uydurma yasağı, belirsizde `[K: ❓ Belirsiz]`, davranış testi varsa AC zorunlu).
  **SPEKÜLASYON YASAĞI:** gözleyemediği sunucu-içi nedeni tahmin etmez ('backend karşılığı ör.
  eksik provider config… olabilir', 'sunucu loglarından bakılmalı', '…gözlemlenemez' gibi olası-neden
  dizisi/gözlem-sınırı meta-notu YASAK); yalnızca gözlemlenen gerçeği yazar (ör. aksiyon→errorCode),
  gerisini kısa açık soruya bırakır. Canlı uygulama (MCP) promptunda da aynı kural
  (`canli_uygulama_baglami_hazirla` → "gözlemlenemeyenleri tahmin etme/sıralama"). Görev-dışı genel
  yorum/'incelenmeli' notu da yazmaz. Sistem Promptları'ndan düzenlenebilir.
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
  `--mcp-config .mcp.live-app.json --strict-mcp-config --allowedTools <16 tarayıcı aracı>`.
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
  console/click/type/**fill_form**/press_key/hover/select_option/wait_for/handle_dialog/tabs/find.
  `browser_evaluate` (keyfi JS), `browser_file_upload`, cookie/localStorage/sessionStorage
  okuma-yazma, `browser_run_code_unsafe`, mouse-seviyesi kontrol, route interception, video/tracing
  bilinçli olarak DIŞARIDA (paket 0.0.78'de bunlar dahil ~65 araç var; yalnızca gözlem için
  gereken dar kapsamlı 16 tanesi allowlist'te — fill_form dahil; login + CRUD formları için).
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

**Verimlilik kuralları (`verimlilik_kurallari`, iki modda da ortak):** tur/token maliyetini düşürmek
için MCP görev metnine eklenir — önce planla + tek geçişte uygula (aynı ekranı tekrar gözlemleme);
snapshot ekonomisi (tam `browser_snapshot` yalnızca DOM anlamlı değişince, öğe bulmak için
`browser_find`); network ekonomisi (liste yalnızca yeni istek tetiklenince, tam detay sadece kritik
istek için); bitiş koşulu (çekirdek gözlem — giriş → aksiyon → istek+yanıt → sonuç → hata — tamamsa
DUR ve raporu yaz). Doğruluk kuralları (CRUD, kayıt formatı, spekülasyon yasağı) aynen geçerlidir.

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


## Task Analizi (Jira görev analizi) — akış detayı
> CLAUDE.md'den taşındı (her-oturum context yükünü azaltmak için). Güncel davranış; değişince burayı güncelle.

**Test düzeltmeleri (analist geri bildirimi):** (a) **Soru mezar-taşı** — `sorular.py` `tumunu_sil()`/`soru_sil()` silinen (id,kaynak) çiftini `data['silinen']`'e yazar; `parse_ve_birlestir` bunları kaynak dosya SİLME zamanından sonra yeniden üretilmedikçe markdown'dan GERİ EKLEMEZ (önceden 'Tümünü Sil' sonrası GET /api/sorular yeniden parse edip geri ekliyordu → 'işlem yapmıyor'). (b) **`/api/oturum` `aktif` bayrağı** — workflow idle ise FALSE; pano VE Analiz Dosyaları (ciktilar) ekranı kalıntı doküman/güncel çıktı dursa bile 'Aktif oturum yok · yüklü doküman' gösterir + 'Kaldır' (`/api/oturum/temizle`: girdi sil + `wf.sifirla`). (c) **Ayarlar CLI hesabı** — `/api/settings.cli_hesap` (`_cli_hesap_oku`, ~/.claude.json'dan e-posta/org; token OKUNMAZ) → CLI'ın hangi hesaba bağlı olduğu Ayarlar'da info. (d) **Pano Yenile** görünür geri bildirim (`panoYenile`, toast). (e) **Jira Ayarları sadeleştirme:** site adresi `jira_site_url()` ile accessible-resources'tan OTOMATİK algılanır — elle `JIRA_URL` yalnız yedek; `/api/jira/config` GET `site_url` döner, UI salt-okunur gösterir + elle giriş 'Gelişmiş' altında; `/api/jira/test` JIRA_URL'i zorunlu tutmaz. Callback URL (`/api/jira/callback`) AYRI şeydir. (h) **Görev analizi format + bağlam filtresi:** `gorev_teknik_analiz` promptu artık ana süreç→teknik analiz formatının AYNI başlık kümesini kullanır (`## 1. Amaç ve Hedefler … ## 11. Kabul Kriterleri`); görevin DOKUNDUĞU başlıklar dolu-somut yazılır, dokunulmayanlar HİÇ AÇILMAZ (boş-başlık/'yok' dolgusu yok). Çekirdek 1/3/11 + FE'de 7, DB'de 4, endpoint'te 5. **Filtre kaydı düzeltmesi:** Task Analizi bağlam filtresini OKUYOR ama ekran KAYDETMİYORDU → `jgAnaliz`/`jgCevaplariIsle` çalışmadan önce `_jgFiltreKaydet` (buildContextFilter→POST) ile ekrandaki filtreyi diske yazar (Süreç 'Başlat' deseni). NOT: `reference/` boşsa anahtar kelime ne olursa olsun RAG 0 döner — zenginlik için önce referans dokümanları senklenmeli. (g) **Task Analizi modalı — ana akış olgunluğu:** üretim/düzeltme sırasında modal-içi JARVIS reaktör (`#jg-proc`, `_jgProcBaslat/_jgProcBitir` + geçen-süre + model readout);  **İlişkili FE/BE analizi:** görevin bağlı task'ları varsa 'Teknik Analiz Et' önce SEÇİM paneli açar (`_jgSecimGoster`): birincil + bağlı task'lar, her biri katman (FE/BE, tahmin `_jgKatmanTahmin`) seçilir. 'Seçilenleri Analiz Et' her task'ı AYRI analiz eder (`jgIliskiliAnalizBaslat` → sıralı `_jgUret`), diğerleri `iliskili_keys` bağlamı olur; karşı katman yalnız `## Bağımlılık ve Arayüz (FE↔BE)` sözleşmesi olarak yazılır (backend `gorev_analiz_et(gorev, iliskili, katman)` + `gorev_getir`). Sonuçlar `_jgAnalizSeti`'te; modal üstünde task DEĞİŞTİRİCİ (`_jgSwitcherRender`/`_jgSonucGoster`), her analiz KENDİ Jira görevine ayrı yazılır. **Açık soru YAKINSAMASI (görev analizi):** `_gorev_acik_sorular_uret(teknik, gorev, cevaplar, onceki_sorular)` — takip turunda ÖNCEKİ tur soruları + analist cevapları prompt'a verilir; cevaplanan/çözülen sorular ÇIKAR, kalan açık olanlar AYNI ID+metinle korunur, yalnız cevapların doğurduğu YENİ bloklayan belirsizlik eklenir (en fazla 6). Böylece sorular turlar içinde AZALIR/biter (drift/tekrar yok). Frontend `jgCevaplariIsle` `onceki_sorular: s.acik_sorular` geçer. **Arka plan iş modeli (görev analizi GÖMÜLÜ + kesintisiz):** analiz/cevap/düzelt/formatla artık `POST /api/jira/gorev/is/baslat` ile arka plan thread'inde çalışır (`_gorev_isler`, `_gorev_is_calistir`); **çok adımlı işlerde adımlar EŞZAMANLI çalışır (P1-C, ThreadPoolExecutor, tavan `GOREV_PARALEL`=3) → ilişkili FE/BE task'ları paralel analiz;** token ölçümü thread-local capture ile adım-başına doğru (`base.token_capture_baslat/al`), Durdur tüm pool thread'lerini killpg eder (`job["worker_tids"]`); UI `_jgIsBaslat`→`/is/durum` polling (`_jgPollDurum`, 2.5sn). Panel MODAL değil GÖMÜLÜ (`#jg-preview-card.jg-inline`, DOMContentLoaded'da `#page-jira-gorevler`'e taşınır); kapatınca (`jgPreviewKapat`) iş DEVAM eder, üstte 'Analiz sürüyor/✓tamamlandı' çipi (`_jgSurenChipGuncelle`), ekrana dönünce `_jgReattach` (localStorage `jg-aktif-job`). 'Durdur' `/is/durdur` — **GERÇEK durdurma (madde 4):** o an süren `claude -p` süreci killpg ile ANINDA öldürülür (`base._cli_calistir` killable Popen + thread-keyed `_CLI_PROC_REG`, `cli_proc_durdur(worker_tid)`); worker `DurdurulduError`'ı iptal sayar. Yan etki: `_cli_calistir` `start_new_session=True` → claude run.py grubundan çıkar, bu yüzden run.py'ye SIGTERM/SIGINT handler eklendi (`cli_tum_durdur()` — `_surec_durdur` killpg'i claude'a bu köprüyle ulaşır). Açık sorular+cevaplar da bu gömülü panelde. **İşlem güvenliği:** üretim/yeniden-yazım/düzeltme sürerken proc başlığı task KEY gösterir; Onayla/Düzelt/Cevapları-İşle PASİF + switcher KİLİTLİ (`_jgSwitcherKilit`) + `_jgSonucGoster`/`jgJiraGuncelle` `_jgAbort` guard'ı → işlem bitmeden başka task içeriği gösterilmez ve Jira'ya YAZILMAZ. (her Q-T-XXX ayrı kart+cevap kutusu; `_jgSorulariAyristir`/`_jgSorulariRender`, yalnız dolu cevaplar `Q-T-NNN: …` olarak toplanır; ayrıştırılamazsa tek-kutu yedeği) (`#jg-cevaplar` → `jgCevaplariIsle` → `/api/jira/gorev/analiz` `cevaplar` param → analiz cevaplara göre yeniden yazılır); **iteratif düzelt** (`#jg-duzelt` → `jgAnalizDuzelt` → `/api/jira/gorev/duzelt` → `gorev_analiz_duzelt`, yalnız ilgili kısım). Sorular/cevaplar Jira'ya YAZILMAZ; Onayla yalnız analiz metnini yazar. (f) **UAT Mutabakat key link'leri:** `jira_site_url` BOŞ sonucu CACHE'LEMEZ (tek geçici hata link'leri süreç boyu kesiyordu); UI `_bsKeyLink` tabanı `_bsSonuc.jira_url || _bsJiraSite` (ekran girişinde `/api/jira/config.site_url`'den çekilir); çoklu-eşleşme önizleme key'leri de linklenir.

## Telemetri + skills modül sorumlulukları — tam metin
> CLAUDE.md klasör-yapısı satırından taşındı. Modül listesi CLAUDE.md'de özet; ayrıntı burada.

- `skills/` iş mantığı (`agent.py` = import bridge): `base.py` (sabitler/RAG/`_api_cagri`/19 prompt), `atlassian.py` (**CANONICAL** OAuth helper), `surec_analizi` `teknik_analiz` `delta_analizi` `brd_analizi` `kapsam_analizi` `jira_tasks` `jira_gorevleri` `backlog_senkron` (**UAT Mutabakat** ekranı — UAT board'u ↔ TRADE/OPS board karşılaştırma; **0-token deterministik**; eşleştirme = mevcut Jira issue-link (UAT linki hedef-projedeki bir key'e işaret ediyorsa o hedef taranan sette olmasa bile `_keyleri_cek` ile çekilip KESİN eşleşmeye dahil edilir — "kapsam dışı hedef") + **Story köprüsü** (UAT ve hedef task AYNI Story/Hikaye'ye bağlıysa dolaylı/transitif eşleşir — `_story_baglari`: Story tipli issue-link VEYA Story tipli **parent** (alt görev doğrudan Story altında); yalnız Story seviyesi, Epic hariç. parser artık `parent_key`/`parent_type` verir) + başlık/içerik Jaccard benzerliği; sonuç UAT sıra no'suna göre artan sıralı; Epic/Story (kapsayıcı) tipler ve UAT board'unda `UAT_HARIC_DURUMLAR` durumları (şu an "Created in Error"/"Create In Error") kapsam dışı; iptal durumları (İptal Edildi/CANCEL/CANCELED — `_iptal_statusu_mu`) ana akıştan ayrılıp ayrı **İptaller** kovasında (`iptaller`) toplanır — JQL `status NOT IN` + elde güvenlik ağı; UAT **ve Hedef** task'larının **atananı** (assignee) da çıktıda (`uat_atanan`/`hedef_atanan`/`atanan`) — her iki taraf için ekranda kolon + Durum/Atanan başlık filtreleri (istemci taraflı, AND); openpyxl ile sıfırdan çok sayfalı .xlsx rapor (`UAT_Mutabakat_*`, Atanan kolonlu). Excel girişi YOK. Not: modül adı `backlog_senkron`, endpoint'ler `/api/backlog/*`, iç sayfa id `backlog-senkron` — tarihsel) `confluence_yaz` `html_mockup` (canlı uygulama Chrome MCP ile gözlemlenip tasarım dili+component'ler baz alınarak, süreç analizindeki ekranlardan çalışan prototip; **sohbetle iteratif düzeltme:** `html_mockup_duzelt(talimat)` mevcut mockup.html + talimat → güncellenmiş HTML, `/api/mockup/duzelt`+`/api/mockup/geri-al` (yedek/undo), UI'da görüntüleyicide "Sohbetle düzelt" satırı — analist istediği hâle gelene kadar düzeltir, "✓ Onayla" ile kabul eder; teknik analiz mockup.html'i kaynak alır) `sorular` `telemetri` (**Kullanım İzleme** — yalnız metadata; analiz olaylarını `logs/usage/events.jsonl`'e append eder + opsiyonel `USAGE_SINK_URL`'e fire-and-forget POST (Google Apps Script→Sheet write-only collector, bkz. `docs/telemetri-apps-script.md`); `istatistik()` 0-token deterministik özet. Emit noktaları: `run.py` (surec/teknik/brd/kapsam/jira_gonder; parent `_bekle` yalnız timeout'ta), app.py in-process endpoint'ler (mutabakat, gorev_analiz, gorev_guncelle, **mockup** `/api/mockup/generate` → olay `mockup`/"Prototip"). **Token/maliyet kaydı (P0):** her AI çağrısı `base.py`'deki süreç-geneli birikimli sayaca girdi/çıktı/cache token + maliyet ekler (CLI: JSON `usage`+`total_cost_usd`; API: `yanit.usage`, `_api_kesilme_uyar` içinden). `base.token_sayac_oku()`/`token_delta(baz)`/`_token_ekle()`. `olay_yaz(..., token={...})` → olaya `token` alanı yazılır. Emit: `run.py` sayaç=koşu toplamı (subprocess taze); app.py `_telemetri_olay(..., token_bas=_token_bas())` → delta. `istatistik()` `token_ozet` (genel) + her analistte `token{}` döndürür. API-cache replay 0 token (messages.create çağrılmaz). **Dashboard'da (P1-A):** `#ku-ozet`'te Token/Maliyet kart grubu (yalnız veri varsa) + analist özet tablosunda Token/Maliyet sütunları + Excel export'ta 4 token sütunu. **KRİTİK:** `_sink_gonder` **SENKRON** POST (daemon thread DEĞİL) — `run.py` gibi kısa-ömürlü subprocess çıkışında daemon thread öldürülüp POST kayboluyordu → süreç/teknik/brd/kapsam Sheet'e HİÇ ulaşmıyordu (yalnız in-process olanlar çalışıyordu). olay_yaz işlem sonunda çağrıldığından senkron bloklama sorun değil. Jira task adedi `telemetri.jira_task_arttir()` ile hem `jira_agent.jira_task_olustur` hem `jira_tasks._issue_olustur`'dan sayılır. Analist kimliği: session username > `ANALYST_NAME` env > OS user, subprocess'e `ANALIST` env ile geçer. **Owner-gate:** `OWNER_KONSOL=true` (AUTH'tan BAĞIMSIZ — analist build'lerinde yoktur → Kullanım+Yetki sekmeleri gizli + `/api/usage/*` 403; `admin_gerekli` AUTH kapalıyken herkesi geçireceğinden ayrı bayrak ZORUNLU). **ESKİ `USAGE_DASHBOARD` bayrağı ARTIK OKUNMAZ** — analist makinelerine kopyalanan owner `.env`'i bu ekranları açıyordu; bayrak `OWNER_KONSOL`'a yenilendi ki kopyalanan eski değer işe yaramasın (analistler güncellemeyle kendiliğinden düzelir; owner `.env`'ine `OWNER_KONSOL=true` ekler). "Kullanım" sekmesi yalnız owner'da; `/api/usage/stats|pull|export`, `auth/me` artık `usage_admin` döner. **Analist kimliği UI'dan:** Ayarlar → "Analist Adı Soyadı" → `analist.json` (gitignore, makineye özel; `/api/analist` GET/POST, owner-gate YOK); analist `.env`'e dokunmaz. Sink URL koda gömülü `VARSAYILAN_SINK_URL` (yalnız-yazma; `USAGE_SINK_URL` env override eder). Kimlik önceliği: login username > `ANALIST` env > `analist.json` > `ANALYST_NAME` env > OS user. Dashboard'da **isim sıralı sabit id** (`istatistik()` analistleri casefold ile sıralayıp 1..N id verir). **Dönem bazlı** (`istatistik(gun, donem, analist)` — gun/hafta/ay trend kovası + tek-analist filtresi; `ozet` bugün/bu-hafta/bu-ay, `trend[]`, `tum_analistler`, `son_tasklar[]`). **Jira key izleme:** `jira_key_ekle()` açılan task key'lerini toplar (jira_gonder → `jira.keyler`+`islem:"acildi"`); görev güncelleme `/api/jira/gorev/guncelle` → yeni olay `gorev_guncelle` (`jira.keyler`+`islem:"guncellendi"`). Excel export'ta **Detay** sayfası (olay-bazlı, key'lerle). HTTP `requests` ile (macOS SSL için — urllib CERTIFICATE_VERIFY_FAILED veriyordu). **Çift sayım önleme:** `olaylari_oku()` — `remote.jsonl` (Sheet, owner dahil tüm ekip) VARSA yalnız onu okur (owner'ın kendi olayı hem lokal `events.jsonl` hem Sheet'te olduğundan aksi halde iki kez sayılırdı); yoksa lokal `events.jsonl`. Owner 'Uzaktan Çek' ile tazeler. Dashboard ölçümleme: **Analist Özeti** (Toplam İşlem/Başarılı/Hatalı/Açılan Task/**Toplam Süre** = efor) + **Analist × Tür matrisi** (kim hangi işi kaç kez; `analistler[].tipler`; TÜM iş tipleri sabit sütun — 0 olsa bile; Teknik Analiz [süreç→teknik] ile Görev Analizi [Jira task-bazlı] ayrı; Excel'de ayrı "Analist × Tür" sayfası) + analist seçilince **tür bazında Ort. Süre** (`analistler[].tip_sure_ms`/adet — farklı tipler ORTALANMAZ, yalnız aynı tip içinde) + legend)). **Not:** `surec_analizi` çıktı formatı analiz ekibinin Confluence şablonudur (AMAÇ/MOCKUP/GEREKSİNİMLER→Ekranlar/ÖNERİLEN DB ALANLARI/GELİŞTİRME NOTLARI); ID'ler + `| Q-001 |` tablosu + `### Süreç Adımları` başlığı pipeline çapası olarak korunur (bkz. docs/MIMARI.md).
