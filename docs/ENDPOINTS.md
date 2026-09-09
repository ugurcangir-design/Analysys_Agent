# Endpoint Kataloğu (app.py — ~86 endpoint)

> Ana referans: [CLAUDE.md](../CLAUDE.md). Bu dosya tam endpoint listesidir;
> yeni/kaldırılan endpoint olduğunda burayı güncelle.

## Çalıştırma / Workflow
```
POST /api/run                  Analiz başlat
GET  /api/workflow-state       Workflow durumu (UI polling 1.5s)
POST /api/approve              Süreç analizi onayı
POST /api/approve-teknik       Teknik analiz onayı (jira ile)
POST /api/approve-teknik-no-jira
POST /api/reject(-teknik)      Reddet
POST /api/rerun                Düzeltme notu ile yeniden çalıştır
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
GET  /api/jira/auth-url            OAuth başlat
GET  /api/jira/callback            OAuth dönüş
POST /api/jira/test                Bağlantı testi
POST /api/jira/hierarchy/preview   AI hiyerarşi önerir (Jira'ya YAZMAZ)
POST /api/jira/hierarchy/create    Analist seçtiklerini Jira'da açar
POST /api/jira/gorevler/cek        FAZ 1: alt görevleri çek + YAPISAL sınıflandır (AI'sız, 0 token)
POST /api/jira/gorevler/siniflandir FAZ 2: yeniden çek + AI ile içerikten sınıflandır (opt-in)
POST /api/jira/gorevler/sadece-client  Yalnızca client (frontend) işlerini ayıkla (batch, opt-in, AI)
POST /api/jira/gorev/formatla      Özellik 1: görevi standart formata çevir (önizleme, YAZMAZ)
POST /api/jira/gorev/analiz        Özellik 2: görevi teknik analizle detaylandır (önizleme, YAZMAZ)
                                   Analist Notu (context_filter → gorev_analist_notu) doluysa dikkate alır
POST /api/jira/gorev/guncelle      Onaydan sonra görev description'ını Jira'da güncelle (markdown→ADF)
```
UI (Jira Görevleri, 0 token / tamamen frontend): "Tüm Görevler" ana başlığı + Jira
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

## Kullanım İzleme (Telemetri — owner-only, 0 token; skills/telemetri.py)
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
GET    /api/sorular[?parse=true]      Soru defteri + istatistik
POST   /api/sorular/parse              Çıktılardan soruları yeniden tara
POST   /api/sorular/<id>               Durum/cevap/varsayım güncelle
DELETE /api/sorular/<id>?kaynak_dosya  Soruyu defterden sil
POST   /api/sorular/tumunu-sil         Tüm soruları sil (opsiyonel {"durum":...} filtresi)
POST   /api/sorular/uygula             Cevapları refine ile analize işle
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
GET  /api/oturum   Aktif oturum: girdi dokümanı, başlangıç (workflow ilk adımı, yoksa girdi mtime),
                   workflow özeti, jira_key; ciktilar[] (etiket/kaynak/var/guncelleme/
                   tazelik=guncel|eski|yok/aktif_versiyon/bekleyen/onayli_revizyon); arsiv[] (history/)
```
Tazelik kuralı: çıktı mtime ≥ oturum başlangıcı → **güncel**, değilse **eski** (önceki oturumdan).
Katalog: `_CIKTI_KATALOGU` (app.py) — yeni çıktı dosyası eklenince buraya da (etiket + köken) eklenir.

## Roller · Görünürlük · Denetim — v2 Faz 2.4 (owner-only; skills/denetim.py)
İki rol: **owner** (AUTH kapalıyken tek kullanıcı; AUTH açıkken `ADMIN_USER`) · **analist** (diğer herkes).
Analist, owner'ın gizlediği ekran/aksiyonlar HARİÇ her şeyi kullanır. `/api/auth/me` artık `rol` + `gizli[]` döner.
```
GET  /api/gorunurluk   Gizlenebilir katalog (GIZLENEBILIR_KATALOG: id/ad/grup/endpoints) + gizli[]
POST /api/gorunurluk   {gizli:[id]} → gorunurluk.json (repoda İZLENİR; analistlere güncellemeyle iner)
GET  /api/denetim      Denetim kaydı, en yeni önce (?islem=&kullanici=&limit=) + tipler[]
```
Sunucu tarafı: `gorunurluk_kontrol` before_request — analist için gizli id'lerin `endpoints` ön ekleri 403.
UI: `_rolUygula()` (index.html) analistte Yönetim grubunu + gizli id'leri (nav + element) saklar.
Denetim emit noktaları: giris/cikis, revizyon_onay/ret/geri_al, yeniden_uret, yeniden_baslat,
guncelleme, kullanici_ekle/sil, gorunurluk → `logs/audit.jsonl` (gitignore'daki logs/ altında).

## Confluence + diğer
```
POST /api/confluence/publish   Markdown → Confluence sayfası
POST /api/confluence/diagnose  Scope/erişim teşhisi
POST /api/mockup/generate      HTML prototip üret
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
