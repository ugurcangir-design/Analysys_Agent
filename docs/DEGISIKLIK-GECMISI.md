# Değişiklik Geçmişi / Tamamlanan İşler (referans)

> Ana referans: [CLAUDE.md](../CLAUDE.md). Tarihsel kayıt — büyük bir faz/özellik
> tamamlandığında buraya özet ekle.

## Faz 1 — Skill ayrıştırma ✅
`agent.py` → 13 satırlık import bridge; tüm iş mantığı `skills/` altında.

## Faz 2 ✅
- **Confluence yazma:** `skills/confluence_yaz.py` + Markdown→Storage Format
- **Jira hiyerarşi:** `skills/jira_tasks.py` — preview/create iki adımlı, FE/BE katman, modal seçim
- **API Şema & DDL:** teknik analiz Bölüm 3 (CREATE TABLE) ve Bölüm 4 (OpenAPI YAML)
- **HTML Prototip:** `skills/html_mockup.py` + mockup.html çıktısı

## Faz 3 ✅
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

## Faz 4 — Teknik analiz kalite + Jira Görevleri ✅
- **Teknik analiz üç aşamalı:** Aşama 1 teknik analiz → kapsam denetimi + AI denetçi → Aşama 2 açık sorular
- **Çıktı kesilme koruması:** `_teknik_uret_tam()` retry + `_xml_ayir` tolerans (CLI erken bitirme)
- **Jira Görevleri sekmesi** (`skills/jira_gorevleri.py`): Epic/Story alt görev triyajı,
  iki fazlı sınıflandırma (yapısal + AI), benzer-içerik tespiti, yorumlar, Standart Formatla
  (Haiku) / Teknik Analiz Et (Sonnet + Haiku açık sorular), tam ekran modal, Jira'ya yazma
- **markdown_to_adf:** HTML yorumlarını siler (RAG meta-yorumu Jira'ya sızmıyor)
