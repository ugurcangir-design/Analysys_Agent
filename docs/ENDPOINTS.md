# Endpoint Kataloğu (app.py — ~86 endpoint)

> Ana referans: [CLAUDE.md](../CLAUDE.md). Bu dosya tam endpoint listesidir;
> yeni/kaldırılan endpoint olduğunda burayı güncelle.

## Çalıştırma / Workflow
```
POST /api/run                  Analiz başlat
GET  /api/workflow-state       Workflow durumu (UI polling 1.5s); `hata_ozet` {kategori,baslik,aciklama,oneri,ozet,ham}|null
                               — analist-dostu hata (skills/hatalar.py, deterministik; UI hata kartı + katlanabilir teknik iz)
POST /api/approve              Süreç analizi onayı
POST /api/approve-teknik       Teknik analiz onayı (jira ile)
POST /api/approve-teknik-no-jira
POST /api/reject(-teknik)      Reddet
POST /api/geri-don             Teknik onayından SÜREÇ onayına geri dön (süreç YENİDEN ÇALIŞMAZ, teknik dosyası korunur; 409 başka durumda)
POST /api/adim/duzelt          Adım sohbeti: {dosya, talimat} → talimattaki ID/bölüm adına göre YALNIZ o bölüm AI ile düzenlenir
                               ve otomatik uygulanır (arka plan; ilerleme GET /api/revizyon/<dosya> `calisiyor`).
                               Bölüm bulunamazsa {tam_uretim_gerekli:true} → UI /api/rerun'ı son çare önerir.
POST /api/rerun                Düzeltme notu ile TAM yeniden çalıştır (son çare)
POST /api/reset                Workflow'u IDLE'a sıfırla
POST /api/heartbeat            UI canlı sinyali (every 20s)
POST /api/shutdown             DESKTOP_MODE'da sunucuyu kapat
```

## Çıktı / Referans
```
GET  /api/outputs              Mevcut çıktıları listele
GET  /api/output/<ad>          İçerik oku
POST /api/output/delete        Çıktıyı sil
GET  /api/reference/list       Referans dosya ağacı
POST /api/reference/upload/<kategori>  kategori: confluence / jira / services / live-app
POST /api/reference/delete
GET  /api/reference/content
POST /api/reference/fetch-be   Backend'den içerik çek
```

## Jira
```
GET  /api/jira/config             {client_id,project_key,jira_url(yedek),site_url(otomatik algılanan gerçek site),cloud_id,connected}
GET  /api/jira/auth-url            OAuth başlat
GET  /api/jira/callback            OAuth dönüş
POST /api/jira/test                Bağlantı testi (JIRA_URL ZORUNLU DEĞİL — site otomatik algılanır)
POST /api/jira/hierarchy/preview   AI hiyerarşi önerir (Jira'ya YAZMAZ)
POST /api/jira/hierarchy/create    Analist seçtiklerini Jira'da açar
POST /api/jira/gorevler/cek        FAZ 1: alt görevleri çek + YAPISAL sınıflandır (AI'sız, 0 token)
POST /api/jira/gorevler/siniflandir FAZ 2: yeniden çek + AI ile içerikten sınıflandır (opt-in)
POST /api/jira/gorevler/sadece-client  Yalnızca client (frontend) işlerini ayıkla (batch, opt-in, AI)
POST /api/jira/gorev/formatla      Özellik 1: görevi standart formata çevir (önizleme, YAZMAZ)
POST /api/jira/gorev/analiz        Özellik 2: görevi teknik analizle detaylandır (önizleme, YAZMAZ). Opsiyonel `cevaplar`:
                                   açık sorulara analist cevapları → analiz cevaplara göre YENİDEN yazılır (belirsizlik çözülür).
                                   Analist Notu (context_filter → gorev_analist_notu) doluysa dikkate alır
POST /api/jira/gorev/duzelt        İteratif düzelt (önizleme, YAZMAZ): {gorev, markdown, talimat} → yalnız ilgili kısmı
                                   düzeltilmiş tam analiz (HTML prototip 'sohbetle düzelt' deseninin görev karşılığı)
POST /api/jira/gorev/guncelle      Onaydan sonra görev description'ını Jira'da güncelle (markdown→ADF)
```
UI (Task Analizi, 0 token / tamamen frontend): "Tüm Görevler" ana başlığı + Jira
statü filtresi (çoklu seçim chip'ler); "Analist Notu" alanı (kalıcı, gorev_analist_notu).

## UAT Mutabakat (UAT board ↔ TRADE/OPS board karşılaştırma — 0 token, deterministik)
```
POST /api/backlog/mutabakat        {uat_proje, hedef_projeler, mod, hedef_keys, anahtar_kelime}
                                   → iki board'u Jira'dan çekip karşılaştırır. mod: tum |
                                   epic (hedef_keys altı) | keyword (anahtar_kelime). Eşleştirme
                                   = issue-link + başlık/içerik Jaccard. Dönüş: eslesenler,
                                   adaylar, eslesmeyen_uat, eslesmeyen_hedef, sayimlar, jira_url.
POST /api/backlog/export           Mutabakat sonucu (POST body) → çok sayfalı .xlsx rapor
                                   (Eşleşenler / Eşleşmeyen UAT / Eşleşmeyen TRADE-OPS). Dönüş: {dosya}.
GET  /api/backlog/indir/<dosya>    Üretilen .xlsx raporu indir (binary send_file)
```
Not: Excel yükleme (`/api/backlog/upload`) ve senkron (`/api/backlog/senkronize`) KALDIRILDI;
eski takip-Excel senkron akışının yerini board-to-board mutabakat aldı.

## Kullanım Raporu (Telemetri — owner-only, 0 token; skills/telemetri.py)
```
GET  /api/auth/me                  → {username, is_admin, usage_admin}. usage_admin = USAGE_DASHBOARD
                                     bayrağı (AUTH'tan bağımsız owner-gate).
GET  /api/analist                  Bu makinedeki analist ad-soyad (analist.json). Owner-gate YOK.
POST /api/analist                  {ad_soyad} → analist.json'a yazar (UI'dan kimlik; .env gerekmez).
GET  /api/usage/stats?gun=90&donem=gun|hafta|ay&analist=<ad>
                                     Owner-only. Dönem bazlı (gün/hafta/ay trend) + analist filtresi.
                                     403 eğer USAGE_DASHBOARD yok. Dönüş: ozet{bugun,bu_hafta,bu_ay},
                                     analistler[] (isim sıralı sabit id), tum_analistler, tip_toplam,
                                     trend[], son_tasklar[] (açılan/güncellenen jira key'leri).
GET  /api/usage/donem-detay?baslangic=YYYY-MM-DD&bitis=YYYY-MM-DD
                                     Owner-only drill-down: verilen tarih aralığı için analist×tür
                                     matrisi + günlük dağılım. Trend'de hafta/ay bloğuna tıklayınca
                                     günler, güne tıklayınca "o gün kim hangi işi yaptı" gösterir.
POST /api/usage/pull               Owner-only. Uzak sink'ten (Apps Script GET, USAGE_SINK_KEY) ekip
                                     olaylarını çekip logs/usage/remote.jsonl'e yazar. Dönüş: {ok, mesaj}.
GET  /api/usage/export?gun=90      Owner-only. .xlsx: Analist Özeti + Tür Kırılımı + **Detay** sayfaları
                                     (Detay = her olay tek satır: tarih-saat, analist, işlem, doküman/proje,
                                     durum, süre, jira key, açıldı/güncellendi).
```
Not: Olaylar `logs/usage/*.jsonl` (gitignore). Emit `run.py` + in-process endpoint'lerden; kurulum
`docs/telemetri-apps-script.md`. `USAGE_DASHBOARD` yalnız owner `.env`'inde → ekip göremez.

## Soru Defteri (skills/sorular.py)
```
GET    /api/sorular                   Soru defteri + istatistik — YALNIZ bu oturuma ait TAZE çıktıların
                                       soruları (bayat/önceki-oturum çıktıları `_oturum_baslangic()` eşiğiyle
                                       elenir → süreç analizi tamamlanmadan hayalet soru olmaz)
POST   /api/sorular/parse              Çıktılardan soruları yeniden tara
POST   /api/sorular/<id>               Durum/cevap/varsayım güncelle
DELETE /api/sorular/<id>?kaynak_dosya  Soruyu defterden sil
POST   /api/sorular/tumunu-sil         Tüm soruları sil (opsiyonel {"durum":...} filtresi) — MEZAR-TAŞI bırakır:
                                       silinen (id,kaynak) parse_ve_birlestir ile markdown'dan GERİ GELMEZ (kaynak
                                       yeniden üretilene kadar). Tekil DELETE /api/sorular/<id> de aynı mezar-taşını bırakır.
POST   /api/sorular/uygula             Cevapları analize işle — ARKA PLANDA (bloklamaz); {ok, baslatildi, toplam}.
                                       HEDEFLİ: `bagli_id` bölümü hedef analizde bulunursa yalnız o bölüm düzenlenir
                                       (revizyon sürümü); bulunamayanlar tam `yeniden_calistir`'a düşer.
GET    /api/sorular/uygula/durum       İlerleme (UI polling): {calisiyor, toplam, tamamlanan, sonuclar[], mesaj, bitti}
GET    /api/sorular/paylasim           Bekleyen soruları metin export
```
Durumlar: `acik / bekleniyor / cevaplandi / atlandi / varsayim`
Kalıcı veri: `output/sorular.json` (atomik yazım)

## Revizyon Oturumu — v2 Faz 1 (skills/revizyon.py + revizyon_ai.py)
Analiz-bağlı, durumlu revizyon: bölüm-hedefli düzeltme (tam yeniden-üretim yok) +
değişiklik geçmişi + onay/ret. `<dosya>` daima `IZIN_VERILEN_CIKTILAR`'da olmalı.
```
GET  /api/revizyon/<dosya>                 Oturum özeti (versiyonlar/geçmiş/bekleyen) + çalışma durumu
POST /api/revizyon/<dosya>/baslat          Mevcut çıktıdan oturum aç (v1=mevcut; idempotent)
POST /api/revizyon/<dosya>/bolum-duzenle   {anahtar, talimat} → bölümü AI ile düzenle (arka plan, BEKLEMEDE öneri)
POST /api/revizyon/<dosya>/onayla          {revizyon_id} → aktif yap + GERÇEK çıktı dosyasına yaz
POST /api/revizyon/<dosya>/reddet          {revizyon_id} → aktif değişmez
POST /api/revizyon/<dosya>/geri-al         {versiyon_id} → eski sürüme dön + çıktıya yaz
GET  /api/revizyon/<dosya>/diff?a=v1&b=v2  İki versiyon arası unified diff
```
Onay durumları: `beklemede / onaylandi / reddedildi`. Mevcut `/api/rerun` (tam
yeniden-üretim) DOKUNULMADAN yanında durur.
Kalıcı veri: `output/revizyon/<slug>.json` + `output/revizyon/<slug>/<vid>.md` (atomik yazım)

## Analiz Oturumu — v2 Faz 2.1 (Çıktılar ekranı; 0 token, deterministik)
```
GET  /api/oturum   Aktif oturum: girdi dokümanı, `aktif` (workflow idle ise FALSE — kalıntı doküman/güncel
                   çıktı dursa bile "aktif oturum yok"), başlangıç (workflow ilk adımı, yoksa girdi mtime),
                   workflow özeti, jira_key, gozlem{yapildi,num_turns,reddedilen,kapsam,zaman}
                   (canlı gözlem makine-doğrulanmış durumu; önceki oturuma aitse null); ciktilar[] (etiket/kaynak/var/guncelleme/
                   tazelik=guncel|eski|yok/aktif_versiyon/bekleyen/onayli_revizyon); arsiv[] (history/)
POST /api/oturum/temizle   Yüklü girdi dokümanını siler + workflow sıfırlar (aktif oturum yokken kalıntıyı kaldır; analiz sürüyorsa 409)
```
Tazelik kuralı: çıktı mtime ≥ oturum başlangıcı → **güncel**, değilse **eski** (önceki oturumdan).
Katalog: `_CIKTI_KATALOGU` (app.py) — yeni çıktı dosyası eklenince buraya da (etiket + köken) eklenir.

## Roller · Görünürlük (Yetki) — owner-only
İki rol: **owner** (AUTH kapalıyken tek kullanıcı; AUTH açıkken `ADMIN_USER`) · **analist** (diğer herkes).
Analist, owner'ın gizlediği ekran/aksiyonlar HARİÇ her şeyi kullanır. `/api/auth/me` artık `rol` + `gizli[]` döner.
Ekran adı: **Yetki** (`screens/yetki.html`; eski "Yetki & Denetim").
```
GET  /api/gorunurluk   Gizlenebilir katalog (GIZLENEBILIR_KATALOG: id/ad/grup/endpoints) + gizli[]   [yetki_gerekli]
POST /api/gorunurluk   {gizli:[id]} → gorunurluk.json (repoda İZLENİR; analistlere güncellemeyle iner) [yetki_gerekli]
```
**Yetki ekranı owner-KURULUM kapısı:** `yetki_gerekli` = `YETKI_PANELI=true` (verilmezse `USAGE_DASHBOARD`'a düşer)
**ve** owner. Kendi makinesine kuran analist AUTH kapalıyken 'owner' sayıldığı için rol yetmez; bayrak analist
kurulumunda yoktur → nav gizli (`auth/me.yetki_admin=false`) + endpoint 403.
```
```
Sunucu tarafı: `gorunurluk_kontrol` before_request — analist için gizli id'lerin `endpoints` ön ekleri 403.
UI: `_rolUygula()` (index.html) analistte Yönetim grubunu + gizli id'leri (nav + element) saklar.
**Denetim (audit) v3'te KALDIRILDI:** `skills/denetim.py` silindi, `_denetim()` no-op, `/api/denetim` +
`logs/audit.jsonl` yok. Analist iş takibi tamamen **Kullanım Raporu** (skills/telemetri).

## Otomatik Güncelleme — v2 Faz 2.5 (bildirimli otomatik)
Arka plan thread'i (`_oto_guncelleme_dongusu`, boot'ta `_oto_guncelleme_baslat`): `AUTO_UPDATE_INTERVAL`
(vars. 600 sn) aralıkla `git fetch`; uzak dal öndeyse **iş yokken** (`_mesgul_mu()` = workflow çalışmıyor +
rerun/revizyon kilidi boş) `pull --ff-only` + pip + `_yeniden_baslat_zamanla()`; iş sürerken 60 sn'de bir
yeniden dener. **Engel:** yerel değişiklik (dirty tree) veya push edilmemiş commit varsa asla otomatik pull
yapmaz (owner geliştirme makinesi) — yalnız bildirir. `.env`: `AUTO_UPDATE=false` kapatır.
```
GET  /api/guncelleme/durum[?kontrol=1]  yeni_surum/behind/ahead/uzak/degisiklikler[]/engel/bekleme_nedeni/uygulaniyor
POST /api/guncelleme/simdi              iş yoksa hemen uygula (engel → 409; iş sürüyor → 409)
```
UI: `screens/_guncelleme.html` (script partial) — 60 sn'de bir sorar; banner "Yeni sürüm hazır · n commit"
+ değişiklik listesi + "Şimdi güncelle"; uygulanınca `/api/version` hash değişince sayfayı yeniler.
Mevcut `/api/update` (elle) ve `/api/restart` dokunulmadan durur.

## Sistem Sağlığı — v2 Faz 2.6 (owner-only; 0 token)
```
GET  /api/saglik   surum{hash,mesaj,tarih,dal} · ai{modu,model,cli_uygun,cli_reset} · guncelleme{otomatik,
                   yeni_surum,behind,engel,son_kontrol} · workflow{durum,calisiyor,mesgul} · mcp{chrome_config,
                   mcp_json,live_app_profil} · disk{output,logs,history,input,reference,.api_cache,backlog: mb,dosya} ·
                   disk_temizlik{dosya_sistemi{toplam_gb,bos_gb,bos_yuzde},temizlenebilir_mb,son,zamanlama} ·
                   auth{aktif,kullanici_sayisi,rol,gizli_sayisi} · ortam{python,flask,port}
GET  /api/pano     HERKES — rol-duyarlı Ana Sayfa "Sıradaki iş": rol · workflow{durum,etiket,calisiyor,tamamlandi} ·
                   onay{adim:surec|teknik|brd,etiket,dosya}|null · sorular{acik,kritik,uygulanmamis} · bekleyen_revizyon[]
GET  /api/disk/durum   owner — {dosya_sistemi, plan{adaylar[],adet,toplam_mb} (KURU), son, zamanlama}
POST /api/disk/temizle owner — planı uygular; analiz sürüyorsa 409. {silinen, kazanilan_mb, hata[]}
```
**Disk temizliği (Faz 3):** `skills/disk_temizlik.py` — kurallar `_KURALLAR` (yalnız yeniden-üretilebilir/arşiv:
`.api_cache/*.txt` TTL, `reference/_filtered_cache` 7g, `reference/live-app` 30g, `logs/*.log(.N)` 30g [son 24 saatte
yazılan aktif log korunur], `backlog/*.xlsx` 30g, `history/*` 60g). `output/`, `input/`, `logs/usage/`, referans
kaynakları DOKUNULMAZ. Zamanlayıcı `_disk_temizlik_dongusu` (app.py): `DISK_TEMIZLIK` / `DISK_TEMIZLIK_ARALIK`,
`_mesgul_mu()` doluysa 5 dk erteler. Durum `logs/disk-temizlik-durum.json`.
UI (v2.1): `/api/saglik` artık **Ana Sayfa** panosunda (`screens/pano.html`) gösterilir — ilk açılışta gelen
dashboard (aktif oturum + **Sıradaki iş** [`/api/pano`, herkes: bekleyen onay adımı / açık-kritik soru /
bekleyen revizyon / çalışan iş] + hızlı eylemler + sağlık [owner: CLI durumu, Disk, **Disk temizlik** kartı + "Şimdi temizle"]). Ayrı "Sistem Sağlığı"
menüsü kaldırıldı. "Geçmiş" menüsü de kaldırıldı — arşiv Çıktılar ekranında. **Komut paleti** `screens/_palet.html` — ⌘K/Ctrl+K veya sidebar arama
kutusu; görünür nav öğeleri (rol gizlemesine saygılı) + hızlı aksiyonlar; klavye ile gezinme.
**Regresyon:** `tests/smoke_test.py` (Flask test client, deterministik uçlar, 27 kontrol) +
`tests/test_revizyon.py` (15) + `tests/test_auth_roller.py` (23) + `tests/test_kod_kaynagi.py` (17).

## Kod Kaynağı — v2 Faz 3.a (salt-okuma; config owner-only; skills/kod_kaynagi.py)
Analizi gerçek koda bağlamanın ALTYAPISI (repo bağlı değilse zarifçe boş; yol-güvenli, 0 token).
Config makineye özel: `reference/kod_kaynagi.json` (gitignore; `.example` seed).
```
GET  /api/kod/repolar   Yapılandırılmış repolar + durum (var/git/branch/commit/dosya/diller)
POST /api/kod/repolar   {repolar:[{ad,yol,aktif}]} → kod_kaynagi.json (owner-only)
GET  /api/kod/agac      ?repo=&yol=  tek seviye ağaç (klasörler+dosyalar; node_modules/venv/.git hariç)
GET  /api/kod/dosya     ?repo=&yol=  dosya içeriği (yol-güvenli, ≤512KB, metin/kod uzantıları)
GET  /api/kod/ara       ?repo=&sorgu=  metin araması (ripgrep varsa; yoksa python fallback)
GET  /api/kod/gecmis    ?repo=&yol=  yola dokunan son git commit'leri
```
Güvenlik: tüm yollar repo köküne hapsedilir (resolve + is_relative_to); yazma/komut YOK. UI: `screens/kod.html`
(Kaynaklar). Gerçek repo bağlantısı analistin isteğine bırakıldı — bağlanınca etki analizi (3.b) dolar.

## Etki Analizi — v2 Faz 3.b (skills/etki_analizi.py; 0 token, deterministik)
```
GET /api/etki/<dosya>[?repo=]   Çıktıdaki teknik varlıklar → (repo bağlıysa) etkilenen dosya/satır
```
Varlık çıkarımı: backtick'li kod terimleri (`snake_case`/`camelCase`), endpoint yolları, yapısal ID'ler
(PA/BR/AC…). repo bağlıysa her varlık `kod_kaynagi.ara` ile aranır → `etkiler[]` (varlık→dosyalar→isabet)
+ `etkilenen_dosyalar[]`. Repo yoksa `kod_bagli:false`, yalnız `varliklar`. Kesin değil — analistin
doğrulaması için ETKİ HARİTASI başlangıcı. UI: Kod ekranında "Etki analizi" paneli.

## Referans Retrieval (BM25) — v2 Faz 3.c-i (skills/retrieval.py; 0 token, dependency yok)
Büyük referanslardan ilgili bölümleri BM25 ile getirir. `base._keyword_odakli_metin` bunu ÖNCE dener
(hata → mevcut keyword-window davranışına düşer). Endpoint yok — analiz yolunun içinde. Türkçe-i (İ→i)
düzeltmeli tokenizasyon. Embedding backend aynı `en_alakali_parcalar` arayüzüyle takılabilir.

## Analiz Veri Kaynakları (Postgres/Jira MCP) — v2 Faz 3.c-ii (owner-only; skills/analiz_mcp.py)
Analiz çağrılarına (`claude -p`) Postgres/Jira MCP + salt-okuma araç izni ekler (canlı-app Chrome MCP deseni).
**Varsayılan KAPALI** — aktif edilmeden hiçbir ek argüman gitmez. Config makineye özel
(`reference/analiz_mcp.json`, gitignore + `.example`); üretilen `.mcp-analiz.json` (bağlantı içerir) da gitignore.
```
GET  /api/analiz-mcp   Durum (aktiflik + hazır sunucular; bağlantı dizesi MASKELİ, sızmaz)
POST /api/analiz-mcp   {postgres:{aktif,baglanti}, jira:{aktif,komut,args}} (boş baglanti → mevcut korunur)
```
`analiz_mcp.cli_argumanlari()` → `--mcp-config .mcp-analiz.json --strict-mcp-config --allowedTools
mcp__postgres__query …`; `_api_cagri_cli`'de canlı-app aktif DEĞİLSE eklenir (--strict tekil). UI: Kod ekranı
"Analiz veri kaynakları" paneli; `/api/saglik` `veri_kaynak`. Gerçek analiz provası: kota + canlı bağlantı (analist).

## Analiz modeli (CLI) — v2.1 (API key gerekmez)
CLI modunda analiz modeli arayüzden seçilir (mevcut Claude.ai aboneliği/lisansı; API key gerekmez).
`base.aktif_cli_model()` `.env`/`os.environ`'dan CANLI okur → değişiklik **yeniden başlatmadan** geçerli
(subprocess `run.py` zaten taze okur; in-process çağrılar + `/api/saglik` görünümü de canlı). Seçenekler:
`CLI_MODEL_SECENEKLER = (sonnet, opus, haiku)`.
```
GET  /api/settings   ... + cli_model (aktif), cli_model_secenekler[], cli_hesap{email,org} (CLI'ın bağlı olduğu Claude hesabı — ~/.claude.json, token OKUNMAZ)
POST /api/settings   ... + cli_model (allowlist doğrulama → CLAUDE_CLI_MODEL .env'e yazılır)
```
UI: Ana Sayfa panosu AI/Kota kartında `<select>` (CLI modunda). `--model` DAİMA açıkça geçilir
(yoksa Claude Code premium varsayılan seçebilir → istenmeyen kota).

## Confluence + diğer
```
POST /api/confluence/publish   Markdown → Confluence sayfası
POST /api/confluence/diagnose  Scope/erişim teşhisi
POST /api/mockup/generate      HTML prototip üret (süreç analizi + opsiyonel canlı gözlem)
POST /api/mockup/duzelt        {talimat} → prototipi SOHBETLE iteratif düzelt (mevcut HTML + talimat →
                               güncellenmiş HTML; sadece istenen değişir). Düzeltmeden önce yedek alınır.
POST /api/mockup/geri-al       Son sohbetli düzeltmeyi geri al (tek adım; yedeği mockup.html'e yazar)
POST /api/sources/sync         Confluence/Jira veri çek
                               (Jira: Backlog/To Do/Cancel statüleri DIŞLANIR —
                                _jira_status_haric_mi + JIRA_HARIC_STATUSLER)
GET  /api/git/status           GitHub güncelleme kontrolü
POST /api/git/pull             git pull --ff-only
GET  /api/prompts              19 prompt + override durumu
POST /api/prompts/<id>         Prompt özelleştirme kaydet
POST /api/prompts/<id>/reset   Varsayılana dön
GET  /api/context-filter
POST /api/context-filter       PATCH semantiği (eksik üst-anahtar korunur): keyword/jira/confluence
                               + live_app + live_app_gorev (target_url/gozlem_kapsami)
                               + live_app_auth + ozel_prompt + gorev_analist_notu
GET  /api/history              Son 5 çalıştırma arşivi
```
