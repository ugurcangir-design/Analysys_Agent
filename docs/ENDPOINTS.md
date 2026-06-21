# Endpoint Kataloğu (app.py — ~80 endpoint)

> Ana referans: [CLAUDE.md](../CLAUDE.md). Bu dosya tam endpoint listesidir;
> yeni/kaldırılan endpoint olduğunda burayı güncelle.

## Çalıştırma / Workflow
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

## Çıktı / Referans
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

## Jira
```
GET  /api/jira/auth-url            OAuth başlat
GET  /api/jira/callback            OAuth dönüş
POST /api/jira/test                Bağlantı testi
POST /api/jira/hierarchy/preview   AI hiyerarşi önerir (Jira'ya YAZMAZ)
POST /api/jira/hierarchy/create    Analist seçtiklerini Jira'da açar
POST /api/jira/gorevler/cek        FAZ 1: alt görevleri çek + YAPISAL sınıflandır (AI'sız, 0 token)
POST /api/jira/gorevler/siniflandir FAZ 2: yeniden çek + AI ile içerikten sınıflandır (opt-in)
POST /api/jira/gorev/formatla      Özellik 1: görevi standart formata çevir (önizleme, YAZMAZ)
POST /api/jira/gorev/analiz        Özellik 2: görevi teknik analizle detaylandır (önizleme, YAZMAZ)
POST /api/jira/gorev/guncelle      Onaydan sonra görev description'ını Jira'da güncelle (markdown→ADF)
```

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
GET  /api/prompts              16 prompt + override durumu
POST /api/prompts/<id>         Prompt özelleştirme kaydet
POST /api/prompts/<id>/reset   Varsayılana dön
GET  /api/context-filter
POST /api/context-filter
GET  /api/history              Son 5 çalıştırma arşivi
```
