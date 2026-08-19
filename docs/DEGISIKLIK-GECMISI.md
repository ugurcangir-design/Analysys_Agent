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

## Faz 7 — UAT Mutabakat: sıra no + sıralı liste + UI iyileştirmeleri ✅
- **Ekran adı** "Backlog Mutabakat" → **"UAT Mutabakat"** (nav/breadcrumb/başlık/KILAVUZ; iç sayfa id
  `backlog-senkron`, modül `backlog_senkron`, endpoint `/api/backlog/*` tarihsel olarak korundu).
  Rapor dosya adı `Backlog_Mutabakat_*` → `UAT_Mutabakat_*`.
- **UAT sıra no + sıralı liste:** her satır UAT key'inin sonundaki sayıyla (`_sira_no`, MBSUATEAM-116→116)
  "Sıra" kolonunda gösterilir; tüm kovalar bu no'ya göre ARTAN sıralanır (eski karışık liste — link
  eşleşmeleri string-sıralı + benzerlik eşleşmeleri oluşturma sırasında — düzeltildi). Export'a da "Sıra".
- **UI (önceki turda):** stat kartları FİLTRE (`bsFiltrele`); satır rozetleri (✓ Eşleşti / ● Aday /
  ✕ Eşleşmedi); durum farkı (UAT≠Hedef) amber+"≠" vurgu; task key'leri Jira browse link (bold + ↗).
- **Doğrulandı:** Eşleşenler 1,16,17…; Eşleşmeyen UAT 140,141,142… artan; Sıra=key no; export "Sıra"
  kolonu (MBSUATEAM-1→1). ruff temiz.

## Faz 8 — Süreç Analizi Confluence şablonu + HTML Prototip canlı-uygulama baz'ı ✅
- Süreç analizi çıktı formatı, ekibin Confluence sayfalarıyla (örn. mbs2/Categories, Retailer Management)
  **aynı iskelete** çevrildi: metadata tablosu → **AMAÇ → MOCKUP → GEREKSİNİMLER** (İş Gereksinimleri↔İş
  Kuralları + Aktörler + numaralı **Ekranlar** [Alan Adı/Buton Adı | Açıklama tabloları] + Süreç Adımları)
  → **ÖNERİLEN DB ALANLARI → GELİŞTİRME NOTLARI** (Sistemler, Kabul Kriterleri, Karar Tabloları, Açık Sorular).
- **B yaklaşımı — pipeline korundu:** eski 13-bölüm akış yapısı yerine ekran-merkezli şablon, ama
  ID'ler (A/BR/PA/AF/EF/EK/AC/Q) bölümlere gömülü → `surec_id_kapsam`/RTM çalışır; `### Süreç Adımları`
  başlığı mermaid çapası; `| Q-001 |` tablosu Soru Defteri çapası korundu. `VARSAYILAN_PROMPTLAR
  ["surec_analizi"]` yeniden yazıldı; `surec_analizi_rol`'daki sabit "Bölüm 8" referansı genelleştirildi.
- **Doğrulandı:** ruff temiz; birleşik prompt "Süreç Adımları"+mermaid+yeni bölümler içeriyor;
  `sorular._TABLO_SORU_SATIR` yeni `| Q-001 |` satırını yakalıyor. Gerçek analiz ÇALIŞTIRILMADI (kota).
- **HTML Prototip canlı-uygulama baz'lı** (`html_mockup.py` + `html_mockup_base`): mockup artık
  context_filter `live_app` URL'i (+ alt URL'ler) tanımlıysa `canli_uygulama_baglami_hazirla()` ile
  Chrome MCP gezinme görevi kurup `_api_cagri(..., canli_uygulama_kapsami="surec")` ile Playwright MCP'yi
  açıyor → gözlemlenen ekranın tasarım dili + component desenleri baz alınıyor; içerik süreç analizinin
  Ekranlar (EK-XXX) bölümünden; tüm component'ler çalışır. URL yoksa generic fallback. `html_mockup_base`'in
  eski "Bölüm 9" referansı yeni formata (GEREKSİNİMLER → Ekranlar) taşındı. `MAX_TOKENS_MOCKUP` 8K→12K.
  Stub testiyle doğrulandı (kapsam="surec" geçiyor, gezinme görevi mesajlarda); gerçek mockup ÇALIŞTIRILMADI.

## Faz 9 — Süreç analizi RAG düzeltmesi + İlişkili/Etki analizi ✅
Şikâyet: süreç analizi referans dokümanı/board'ları dikkate almadan yüzeysel çıktı üretti.
- **Kök neden (PDF filtre bug'ı):** confluence referansı olarak konan `TradePanel_1_7_9.pdf` (6.7 MB),
  `filtrele_referanslar`'da `read_text` ile binary okunup keyword eşleşmezdi → RAG'e HİÇ girmezdi.
  `_filtre_metni_oku` (PDF-farkında, `pdf_oku`/fitz) eklendi; confluence filtresi dosya adı VEYA içerik
  eşleşmesiyle dahil ediyor (ilgili farklı-adlı sayfa da gelir).
- **Kök neden 2 (baştan kesme):** ilgili bölüm PDF'in %25'inde (209K/836K); RAG dosya başına ilk 15K'yı
  okurdu → kaçardı. `_keyword_odakli_metin` eklendi: büyük dosyada baştan kesmek yerine keyword geçen
  yerlerin etrafından pencereler alır. Doğrulandı: RAG bloğu artık "publish overview" bölümünü içeriyor.
- **İlişkili/Etki:** `surec_analizi`'ye **İlişkili Ekranlar / Süreçler ve Etki Analizi** (IB-XXX) bölümü +
  **KAYNAK KULLANIMI (ZORUNLU)** bloğu eklendi; `surec_analizi_rol`'a "İLİŞKİ & ETKİ" çalışma adımı.
- **Veri boşluğu (kullanıcı tarafı):** `reference/jira` boş (board senkronu yok) → agent board kullanamaz;
  ayrıca 6.7 MB PDF yerine ilgili Confluence sayfalarını .md senkronlamak RAG için daha isabetli.
- **Doğrulandı:** ruff temiz; boot OK; RAG zinciri "publish overview" içeriyor. Gerçek analiz ÇALIŞTIRILMADI.
- **Confluence sync 404 bug'ı (`atlassian_get`):** Referans güncellemede
  `404 ... /ex/confluence/{cloud}/wiki/api/v2/spaces?keys=mbs2` hatası. Kök neden: OAuth token süresi
  dolduğunda Atlassian **Confluence gateway'i 401 yerine 404 döndürüyor** (Jira 401 döner → refresh
  çalışır; Confluence 404 → eski kod refresh tetiklemez). `atlassian_get` artık confluence'ta **404'te de**
  token yenileyip bir kez tekrar deniyor; hâlâ 404 ise gerçek bulunamadı. (Space key "mbs2" geçerli —
  taze token'la 200/results=1; case sorunu yoktu.) Doğrulandı: atlassian_get mbs2 space'ini buluyor.

## UAT Mutabakat — Durum kolonu hızlı filtresi ✅
Eşleşenler ve Teyit bekleyen adaylar tablolarında (`_bsTabloEsles`, templates/index.html) iki **Durum**
başlığı artık her tablodaki mevcut Jira durumlarıyla dolu bir `<select>` filtresi. UAT Özet sonrası
(uat_durum) ve Hedef Özet sonrası (hedef_durum) kolonlar bağımsız seçilir, birlikte **AND** olarak süzer;
seçime uygun kayıt yoksa "Seçilen duruma uygun kayıt yok" satırı çıkar. Deterministik/istemci-taraflı
(satırlarda `data-fuat`/`data-fhedef` normalize değerler; token harcamaz). Doğrulandı: mock veriyle 2 select
+ doğru benzersiz seçenekler, tek/çift kolon süzme ve boş-durum mesajı çalışıyor; ruff temiz.

## UAT Mutabakat — "Create In Error" UAT taskları kapsam dışı ✅
`skills/backlog_senkron.py`: UAT board'undan (MBSUATEAM) çekilen tasklar artık `UAT_HARIC_DURUMLAR`
(şu an `["Create In Error"]`) durumlarını hariç tutuyor — hatalı/iptal kayıtlar mutabakata girmesin.
JQL'e `AND status NOT IN ("Create In Error")` eklendi; ayrıca özel workflow'da durum adı eşleşmezse diye
çekilen kayıtlarda `casefold` ile **elde güvenlik ağı** filtresi var. Hedef (TRADE/OPS) tarafı etkilenmez.
Doğrulandı: ruff temiz, JQL doğru üretiliyor, import/boot OK.

## UAT Mutabakat — "Created in Error" yazım varyantı da hariç ✅
`UAT_HARIC_DURUMLAR` artık `["Created in Error", "Create In Error"]` — Jira board'unda görülen gerçek
statü "Created in Error" (`-d`'li). Tablodaki "≠" statünün parçası değil, UAT≠Hedef fark işaretidir.
Elde güvenlik ağı casefold ile büyük/küçük harf varyantlarını da yakalar.

## UAT Mutabakat — Durum filtresi: seçenek temizliği + görsel iyileştirme ✅
- **"Created in Error" seçeneği kaldırıldı:** `_BS_FILTRE_HARIC` (backend `UAT_HARIC_DURUMLAR` ile hizalı)
  ile bu durumlar dropdown seçeneklerinden de elenir — kapsam dışı statü filtre listesinde görünmez.
- **Dropdown UX/görsel:** özel ok imi (SVG caret), huni ikonlu büyük-harf "DURUM" etiketi, hover/focus
  vurgusu; filtre seçiliyken `.is-aktif` ile accent kenarlık + tint arka plan → hangi kolonun süzüldüğü
  bir bakışta belli. Doğrulandı: "Created in Error" seçeneklerde yok, huni ikonu render, aktif sınıf
  seçince eklenip boşalınca kalkıyor (tarayıcı mock testi + görsel).

## UAT Mutabakat — Atanan (assignee) kolonu + filtre & dropdown görsel düzeltmesi ✅
- **Atanan kişi:** UAT task'ının assignee'si backend çıktısına eklendi (`_satir.uat_atanan`, `_sade.atanan`;
  parser zaten `assignee`=displayName veriyordu). Eşleşenler/Adaylar ve Eşleşmeyen UAT tablolarında
  **Atanan** kolonu (boşsa soluk "—"), Excel raporuna da yazılıyor (Eşleşenler sayfası "UAT Atanan",
  Eşleşmeyen UAT sayfası "Atanan").
- **Atanan filtresi:** başlıkta hızlı filtre; "Herkes" + benzersiz kişiler + "(Atanmamış)" seçeneği.
  Durum filtreleriyle birlikte **AND** çalışır (hem duruma hem atanan kişiye göre süzme).
- **Genel filtre altyapısı:** `_bsDurumFiltreTh/_bsDurumFiltrele` → generic `_bsFiltreTh(tid, alan, kaynak,
  etiket, satirlar, opt)` + `_bsFiltrele(tid)`; data-attr (`fuat/fhedef/fatanan/fdurum`) ile kaynak alan
   adı ayrıştırıldı. "(Atanmamış)" için `_BS_BOS='__bos__'` sentinel (boş değere eşleşir).
- **Dropdown görsel (görev 1):** sabit yükseklik (26px, box-sizing), özel caret hep görünür, aktif hâlde
  yalnız accent kenarlık+tint (eski şişkin inset gölge kaldırıldı), `vertical-align:bottom` ile hizalı,
  ellipsis. Ekranda taşma/boyut sorunu giderildi.
- Doğrulandı: ruff temiz; tarayıcı mock testinde durum+atanan+atanmamış filtreleri ve AND kombinasyonu
  doğru; görsel ekran görüntüsüyle onaylandı. **Not:** eski bir düzenlemede string'e kazara NUL (\x00)
  girmişti — Python ile temizlendi (`_BS_BOS='__bos__'`).

## UAT Mutabakat — Hedef (TRADE/OPS) atanan kolonu + filtresi ✅
Eşleşenler/Adaylar tablosunda Hedef tarafı için de atanan eklendi: `_satir.hedef_atanan`, Excel'de
"Hedef Atanan" sütunu. Frontend'de Hedef Durum'dan sonra **Atanan** kolonu + `fhatanan` filtresi
(`hedef_atanan` kaynağı; "Herkes"/kişiler/"(Atanmamış)"). Böylece tabloda dört bağımsız filtre
(UAT Durum, UAT Atanan, Hedef Durum, Hedef Atanan) AND mantığıyla birlikte çalışır — UAT durumu +
Hedef atananı gibi çapraz kombinasyonlar dahil. (Eşleşmeyen TRADE/OPS tablosunda atanan+filtre zaten
`_sade.atanan` ile mevcuttu.) Doğrulandı: ruff temiz, tarayıcı mock testinde 4 filtre + çapraz AND +
"(Atanmamış)" doğru, görsel onaylandı.

## UAT Mutabakat — İptal kovası + Epic/Story eleme ✅
- **Epic/Story kapsam dışı:** her iki board'da kapsayıcı tipler (`_KAPSAYICI_TIP_ADLARI` → epic/story/…)
  `_kapsayici_tip_mi` ile elenir; yalnızca yaprak iş kalemleri karşılaştırılır.
- **İptal kovası:** iptal statüsündeki task'lar (İptal Edildi / CANCEL / CANCELED — mevcut
  `_iptal_statusu_mu`) `_iptal_ayir` ile ana akıştan çıkarılıp ayrı **`iptaller`** kovasına alınır
  (UAT+Hedef birlikte, Proje sütunlu). Eşleşen/açıkta kalan listeleriyle karışmaz.
- **Ekran:** yeni "İptal Edildi" stat kartı (mor, tıklayınca yalnız İptal Edilenler kutusu) + `bs-g-iptal`
  grubu; `_bsTabloTek` artık `opt` alıyor (`rozet:false` → "Eşleşme" kolonu gizli, `bosMesaj`). İptal
  kutusunda Durum+Atanan filtreleri var (durum filtresi CANCEL/CANCELED/İptal varyantlarını ayırır).
- **Excel:** yeni "İptal Edilenler" sayfası; Eşleşmeyen TRADE-OPS sayfasına da "Atanan" sütunu eklendi.
- Doğrulandı: ruff temiz; backend simülasyonda Epic/Story elenmesi + 3 iptal varyantı doğru; tarayıcıda
  kart/kutu/filtre ve "yalnız iptaller" izolasyonu ekran görüntüsüyle onaylandı.

## UAT Mutabakat — KESİN eşleşme gerekçesi: ilişki/bağlılık türü + yön ✅
Eşleştirme kuralı değişmedi; yalnızca gerekçe zenginleşti. KESİN (mevcut Jira bağlantısı) eşleşmelerde
`_iliski_sinifi` ile bağın türü sınıflanıyor: **bağlılık** (block/depend/clone/duplicate/cause/split
ipuçları) ↔ gevşek **ilişki** (relates). Gerekçe artık link'in GERÇEK yönünü gösteriyor:
`Jira <tür>: <kaynak> "<ilişki>" <hedef>` (örn. hedef tarafında bulunan link'te "MBSTRADE-9 blocks
MBSUATEAM-2"). `kesin_ciftler` değeri (kaynak_key, ilişki, hedef_key) tuple'ına çevrildi. Metin mevcut
"Gerekçe" kolonuna ve Excel'e otomatik akar (yeni kolon/kova yok). Doğrulandı: ruff temiz; sınıflandırıcı
İng/TR varyantlarda doğru; UAT-tarafı/hedef-tarafı/relates senaryolarında yön doğru.

## UAT Mutabakat — kapsam dışı ama linkli hedef task'lar eşleşmede (bug fix) ✅
**Sorun:** MBSUATEAM-124, MBSTRADE-1404'e Jira "relates to" ile bağlı olmasına rağmen "Eşleşmeyen UAT
(açıkta kalan iş)" görünüyordu. Kök neden: KESİN eşleşme yalnızca hedef task **taranan sette**
(`hedef_index`) ise kuruluyordu; epic/keyword modunda ya da alt-görev gibi durumlarda linkli hedef task
sette olmayınca eşleşme kaçıyordu.
**Çözüm:** Fetch sonrası, UAT task'larının hedef-projedeki (MBSTRADE/MBSOPS) key'lere olan ama `hedef_index`'te
olmayan linkleri toplanır; bu key'ler `_keyleri_cek` (bulkfetch) ile tek tek çekilip `link_hedef_index`'e
alınır (Epic/Story ve iptal olanlar hariç). KESİN eşleşme artık `hedef_index` VEYA `link_hedef_index`'e
bakar; satır bu birleşik kaynaktan kurulur. Bu ek hedefler similarity/eşleşmeyen_hedef'e katılmaz, board
toplamını şişirmez; gerekçeye "· kapsam dışı hedef" notu eklenir. Doğrulandı: gerçek MBSUATEAM-124 →
MBSTRADE-1404 artık KESİN eşleşiyor (hedef boş sette bile); ruff temiz. Not: "tüm board" modunda hedef
zaten sette olduğundan ek sorgu no-op.
