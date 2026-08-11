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

## Faz 5 — Backlog Senkron + Jira Görevleri iyileştirmeleri ✅
- **Backlog Senkron** (`skills/backlog_senkron.py` + `page-backlog-senkron` + 3 endpoint): Product'ın
  UAT board'unda (MBSUATEAM) açtığı taskların TRADE/OPS karşılıklarını takip Excel'ine işler.
  **0 LLM tokenı — tamamen deterministik** (yalnızca Jira REST + Excel). Bağ: UAT --relates to-->
  TRADE/OPS. Değişmeyene iş yapmaz (yan durum dosyası ile `updated`+eşleme kıyası). Tek agent-kolonu
  **UAT - BOARD EŞLEME** (EŞLENDİ/EŞLENMEDİ; Jira linki VEYA kolon Q'daki manuel MBSUATEAM referansı).
  **Cerrahi lxml zip yazımı:** hücre-içi görseller (richData), Excel Tablosu, hyperlink'ler bit-bit
  korunur (openpyxl bunları düşürüyordu); yeni satır/kolonlar tabloya dahil edilir (ref+autoFilter+CF
  genişletme → renk/filtre korunur). Orijinal ezilmez; zaman damgalı kopya. Bağımlılık: `openpyxl`, `lxml`.
- **Jira Görevleri — "Tüm Görevler" + statü filtresi** (UI, 0 token): sonuç alanının üstünde tüm
  görevleri listeleyen ana başlık + dinamik Jira statü chip'leri (çoklu seçim). Mevcut iki başlık
  (Hızlı İşleme / Detaylı Analiz) + arama + AI Sınıflandır + Sadece Client korunur.
- **Jira Görevleri — Analist Notu** (`context_filter → gorev_analist_notu`): opsiyonel, kalıcı alan;
  doluysa "Teknik Analiz Et" notu mevcut promptla BİRLİKTE dikkate alır (doğruluk kurallarını
  gevşetmeden), boşsa yok sayar. Yalnızca teknik analizi etkiler.
- **Sadece Client İşleri** (`/gorevler/sadece-client`): BFF/BE değişikliği gerektirmeyen, yalnızca
  frontend görevleri batch (20'lik) AI ile ayıklar; bağlı BE task'ları dikkate alır.
- **Görev listesi export:** üç grup (+ Tüm Görevler) için kopyala/CSV (anahtar + başlık).
- **Bulkfetch tazelik:** görev/backlog çekiminde `search/jql` yerine `issue/bulkfetch` — arama indeksi
  eventually-consistent olduğundan güncel içerik anında görünür.
- **Görev-bazlı YALIN teknik analiz** (`gorev_teknik_analiz` promptu): ağır 11-bölüm şablonu yerine
  yalnızca ilgili kısımlar (token/süre tasarrufu). Spekülasyon yasağı eklendi.
- **Canlı gözlem MCP verimlilik kuralları:** tek geçiş, snapshot/network ekonomisi, bitiş koşulu →
  görev bazlı canlı gözlem süresi/token maliyeti düşürüldü (doğruluktan ödün yok).
- **Açık renk tema okunabilirliği (WCAG AA):** `--text3` 5.3:1 vb. kontrast düzeltmeleri.
- **CLI 401 OAuth teşhisi:** `_cli_oturum_hatasi_mi` → Türkçe yeniden-giriş rehberi.

## Faz 6 — Backlog Senkron → Backlog Mutabakat (yeniden tasarım) ✅
Ekran, elle yüklenen takip-Excel senkronundan **board-to-board mutabakat** aracına dönüştürüldü.
- **Excel yükleme + senkron kaldırıldı** (`/api/backlog/upload`, `/api/backlog/senkronize`, cerrahi
  lxml zip yazımı). `skills/backlog_senkron.py` baştan yazıldı; eski takip Excel'leri ve
  `senkron_state.json` silindi (git'te hiç izlenmemişti — `backlog/` gitignore).
- **`mutabakat()`** (0 token): UAT board'unu tam tarar, hedef board'ları `mod`'a göre toplar
  (`tum`/`epic`/`keyword`), katmanlı eşleştirir: KESİN (mevcut issue-link) → YÜKSEK (Jaccard ≥ 0.55) →
  ADAY (0.35–0.55) → EŞLEŞMEYEN (UAT = açıkta kalan iş, hedef = kaynağı UAT'de yok). `jira_gorevleri`'nden
  `_issue_ayrıstir` + `_benzerlik_jetonlari` + `alt_gorevleri_cek` yeniden kullanıldı.
- **`rapor_uret()`** (`/api/backlog/export`): openpyxl ile sıfırdan çok sayfalı `.xlsx` (Eşleşenler /
  Eşleşmeyen UAT / Eşleşmeyen TRADE-OPS). Yeni dosya olduğu için cerrahi yazıma gerek yok.
- **`_jira_site_url()`:** browse link'leri için site adresini accessible-resources'tan cloud_id
  eşleşmesiyle alır (cache'li); `.env JIRA_URL`'e güvenmez (OAuth callback tutabiliyor).
- **UI:** kaynak/kapsam formu (UAT + hedef board + tarama modu), 6 stat kartı, 4 sonuç tablosu
  (link'li, güven rozetli), Excel Raporu İndir. Nav/breadcrumb "Backlog Mutabakat".
- **Gerçek veriyle doğrulandı:** UAT=209, hedef=1747 → 174 eşleşen, 1 aday, 42 açıkta kalan UAT,
  1588 eşleşmeyen hedef; rapor + indirme uçtan uca çalışıyor.
