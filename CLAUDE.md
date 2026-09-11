# brd-analyst-agent (Analyst Studio) — Claude Code Context

macOS masaüstü uygulaması. BRD/süreç dokümanı → RAG destekli analiz → Jira Epic/Story/Subtask.
Flask + Python **3.10+** (`str|None`), tarayıcı SPA `http://localhost:5002`.
İki akış: **Süreç → Teknik → Jira** (ana, FE/BE ayrımı) · **BRD → Kapsam**.

## ⚠️ Bu çalışma alanı = v2 KLONU (`brd-analyst-agent-v2`, dal `v2`, port **5003**)
Bu dizin, üretimdeki eski uygulamanın (`/Users/dt/brd-analyst-agent`, port **5002**, dal `main`)
**paralel klonudur**. Eski uygulamaya ve 5002'ye **dokunulmaz** — analistler kesintisiz kullanır.
Tüm v2 geliştirmesi burada, ayrı portta (`PORT=5003 ./start.sh`) yapılır. Rollback çapası:
`v1-stable` etiketi. Yol haritası (çapa, önce oku): **`docs/ROADMAP-V2.md`**.
- **Ekran-eklenebilir arayüz** (Faz 0): ekran page blokları `templates/screens/*.html` partial'larına
  çıkarılıp `index.html`'de `{% include %}` edilir — bkz. `templates/screens/README.md`.
  İlk çıkarılan ekran: `kilavuz`. Kalan ekranlar Faz 2'de kademeli taşınır.
- **Faz 1 — Revizyon oturumu:** `skills/revizyon.py` (deterministik: versiyon/geçmiş/onay/geri-al/diff,
  `output/revizyon/`) + `skills/revizyon_ai.py` (`bolum_duzenle`: yalnız hedef bölüm AI'a gider) +
  `/api/revizyon/*` + `screens/revizyon.html`. Tam yeniden-üretim (`/api/rerun`) dokunulmadan yanında durur.
- **UI v3 — görsel yeniden tasarım (tüm ekranlar, YALNIZ v2):** `index.html` `:root`/`[data-theme]` token'ları
  yeniden palete çevrildi — yumuşatılmış slate + **indigo** aksan (koyu `#6366F1` / açık `#4F4DD6`), yüksek metin
  kontrastı, 10px köşe. Başlıklarda **Space Grotesk** (`--font-display`; Geist gövde + Geist Mono veri korundu).
  **Renk anlamı:** kırmızı `--run` = çalışan işlem · amber `--yellow` = analist sırası/onay (`.status-waiting`) ·
  yeşil = başarı · indigo = marka/aksiyon. Token-tabanlı olduğu için değişiklik tüm ekranlara yansır.
  **Yeni bileşenler (index.html):** üst barda kalıcı **işlem çipi** `#run-chip` (her ekranda; `_updateRunChip(s)`
  ile `updateUI`'den beslenir — running→kırmızı+süre / bekliyor→amber "Onayınızda"; tıkla→HUD veya pipeline) +
  tam-ekran **İşlem Modu HUD** `#islem-modu` (JARVIS tarzı kırmızı reaktör; `islemModuAc/Kapat`, Esc kapatır —
  kapatınca iş arka planda sürer). "hazırlanıyor" analiz görseli de kırmızıya çekildi. Tasarım kanvası:
  artifact a6929f23. **5002/main'e asla uygulanmaz.**
- **UI v3 — ekran/menü düzeni & yeniden adlandırmalar (YALNIZ v2):**
  **Açılır-kapanır sol menü** (`sidebarAcKapa()` → `.layout.sidebar-collapsed`, localStorage `sidebar-collapsed`) +
  **grup başlıkları katlanır** (`navBolumAcKapa()`, chevron, localStorage `nav-collapsed-<grup>`; rol-gizli item'lar
  `rol-gizli` sınıfıyla açılışta sızmaz). **Analist kimliği** sol alt (`#analist-kimlik`: `#ak-avatar`/`#ak-ad`/`#ak-rol`)
  + üst-bar avatarı (`#topbar-avatar`) → `/api/analist`'ten boot'ta + Ayarlar kaydında (`_analistKimligiUygula`).
  **Ana Sayfa (`pano.html`)** kart tabanlı: hızlı-eylem kartları + sistem-sağlığı kart ızgarası (`.pano-cards`/`.pano-card`).
  **Yeniden adlandırma:** "Jira Görevleri" → **Task Analizi** (iç tab anahtarı `jira-gorevler` KORUNDU; endpoint/id değişmedi),
  "Kullanım" → **Kullanım Raporu**, "Yetki & Denetim" → **Yetki**. **Kılavuz menüden kaldırıldı** — üst-bar **?**
  düğmesi (`switchTab('kilavuz')`) açar; sağ-üst Ayarlar düğmesi kaldırıldı (menüde zaten var).
- **Form dili — TEK tutarlı giriş stili (tüm ekranlar):** giriş alanları için form-reset tabanı
  (`input[type=...]`, `textarea`, `select` + `.field-input`/`.ctx-input`/`.setting-input`/`.form-group input`)
  → hiçbir giriş tarayıcı-varsayılanı (beyaz) kalmaz; `--surface2` zemin, `--border-strong`, 13px, 8×11 padding,
  indigo focus ring. Yeni bir input tipi eklerken bu tabana düşer (bespoke sınıf daha yüksek özgüllükle ezer).
  Yardım metinleri (`.field-sub/.field-hint/.ctx-field-sub/.jg-sub/.la-ipucu`) okunaklılık için `--text2`,
  12px, satır-yüksekliği 1.55, `max-width` ile sınırlı — soluk/küçük değil.
- **Denetim (audit) KALDIRILDI (v3):** `skills/denetim.py` silindi, `_denetim()` no-op, `/api/denetim` endpoint'i +
  `logs/audit.jsonl` + `/api/saglik` `denetim{}` alanı + Yetki ekranındaki Denetim paneli kaldırıldı. Analist iş
  takibi tamamen **Kullanım Raporu**'ndadır (`skills/telemetri`). Görünürlük (Yetki) yönetimi aynen durur.
- **Sağlamlaştırmalar (v3 inceleme):** (1) `base._api_cache_key` CLI modunda `aktif_cli_model()`'i anahtara katar →
  model değişince (Sonnet→Opus) eski sonuç yanlış "önbellek hit" dönmüyor. (2) `base.api_cagri_kapanisli(sistem,
  mesajlar, kapanis, ...)` — birleşik XML çağrılarında (BRD `</brd_sorular>`, Kapsam `</alternatif_surecler>`)
  kapanış-etiketi retry'ı → ikinci blok limitte kesilirse sessizce kaybolmuyor (teknik analizdeki `_teknik_uret_tam`
  deseni). (3) `/api/sorular/uygula` artık ARKA PLANDA (daemon thread + `/api/sorular/uygula-durum` polling) —
  bloklayan refine istek thread'ini tutmuyor. (4) `kod_kaynagi.ara` ripgrep hata verse de Python fallback çalışır.
  (5) **Durdur GERÇEKTEN durdurur:** `/api/reset` → `_surec_durdur()` çalışan alt-süreci PROCESS GRUBUYLA
  (`os.killpg`, `start_new_session`) öldürür SONRA `wf.sifirla()`. Eskiden yalnız state sıfırlanıyordu →
  subprocess sürüp durumu geri yazıyordu ("analiz kendi başlıyor"). `_durduruldu` bayrağı `_bekle`'nin bunu
  hata sanmasını önler; UI `resetWorkflowUI()` run-chip'i temizler + HUD'u kapatır. (6) `/api/sorular/uygula/durum`
  3-segmentli — 2-segmentli olsaydı dinamik `/api/sorular/<id>` (POST/DELETE) ile çakışıp GET 405 verirdi.
  (7) Küçük etiket/çip okunaklılığı (`.panel-tag`/`.ds-chip`/`.ds-panel-tag`/`.ctx-active-badge`) `--text2`+büyütüldü,
  "aktif" → büyük harf pill. (8) **Yeni yükleme = yeni oturum:** `/api/upload` artık `wf.sifirla()` yapar
  (çalışırken 409 verir) → bayat "onay_bekleniyor"/tamamlandı durumu yeni dokümana taşınmaz. (9) **Sorular
  tazelik filtresi:** `parse_ve_birlestir(taze_esik)` yalnız bu oturuma ait (mtime ≥ `_oturum_baslangic()`) TAZE
  çıktıların sorularını gösterir; bayat/önceki-oturum soruları düşürülür — süreç analizi tamamlanmadan hayalet soru
  görünmez (tüm analiz tipleri). `/api/sorular` her zaman filtreli döner. (10) **Ekran adları:** "Çıktılar" →
  **Analiz Dosyaları**, "Görüntüleyici" → **Çıktı Dosyaları** (iç tab anahtarları `ciktilar`/`output` korundu).
  (11) **Yetim workflow uzlaştırması:** `/api/oturum` — workflow "settled" (onay_bekleniyor/teknik_onay/
  brd_revize/tamamlandi) ama çalışmıyor ve **0 güncel çıktı** varsa (çıktı önceki oturumdan) → `wf.sifirla()` +
  idle. Dashboard/Çıktılar/üst-bar tutarsız "Analist onayı bekleniyor + GÜNCEL ÇIKTI 0" göstermez; legit onay
  (≥1 güncel çıktı) korunur, çalışan analize dokunulmaz.
  (12) **Kanıt çipleri + Gözlem rozeti (Faz 1):** Çıktı Dosyaları'nda markdown render sonrası `_kanitCipleriIsle`
  `[K: …]` kaynak etiketlerini renkli çipe çevirir (gerçek veri=yeşil · Confluence=mavi · BRD=nötr · Jira=indigo ·
  türetilmiş=amber · kaynaksız=kırmızı) + üstte özet sayaç ("N etiket · X gerçek · ⚠ Y doğrulanmalı") — yalnız metin
  düğümlerinde, `code/pre` hariç. `_api_cagri_cli` canlı-gözlem sonucunu `output/.gozlem-durum.json`'a yazar
  (`_gozlem_durum_yaz`: yapildi/num_turns/reddedilen — makine-doğrulanmış); `/api/oturum` `gozlem` alanı (yalnız bu
  oturuma aitse) → süreç/teknik çıktısında "🌐 Canlı gözlem yapıldı · N tur" / "⚠ YAPILAMADI" rozeti.
  (13) **Adım sohbeti + geri dönüş (Faz 2 — "önceki adımı yeniden çalıştırmak zorunda kalma"):** onay
  kapılarında (`#surec-act-onay`, `#surec-act-teknik-onay`) tek satırlık **"Bu adımı düzelt"** kutusu →
  `POST /api/adim/duzelt {dosya, talimat}`: hedef dosya ADIMDAN bellidir (niyet yönlendirme YOK); hedef bölüm
  talimattaki yapısal ID (`_ADIM_ID_DESEN`: PA/BR/EK/EF/AF/AC/FR/NFR/Q/PO/T-FE/T-BE-nnn) ya da bölüm başlığı
  kelimesinden türetilir (`_adim_hedef_bolum`) → yalnız o bölüm `revizyon_ai.bolum_duzenle` ile düzenlenir ve
  **otomatik `revizyon.onayla`** (sürüm oluşur, Revizyon ekranından Geri Al). Bölüm bulunamazsa
  `tam_uretim_gerekli` döner → UI analiste ID eklemesini ya da "Tam yeniden üret" (eski `/api/rerun`, artık
  `<details>` içinde SON ÇARE) önerir; asla sessizce tümü yeniden yazılmaz. **"◂ Süreç analizine dön"**
  (`POST /api/geri-don` → `wf.surec_adimina_geri_don()`, yeni geçiş TEKNIK_ANALIZ_ONAY_BEKLENIYOR→
  ONAY_BEKLENIYOR): süreç analizi YENİDEN ÇALIŞMAZ, teknik-analiz.md silinmez; analist süreçte hedefli
  düzeltir, "Devam Et" teknik analizi yeniden üretir. **Soru cevapları hedefli:** `/api/sorular/uygula` →
  `_sorulari_hedefli_uygula`: `bagli_id` bölümü analiz dosyasında (`_SORU_HEDEF_ANALIZ`: acik-sorular→
  teknik-analiz, brd-sorular→brd-analizi) bulunursa yalnız o bölüm düzenlenir; bulunamayanlar toplanıp
  `yeniden_calistir`'a düşer (`sonuclar[].hedefli/tam_uretim`).
- **Kaynak-öncelik sırası (KANONİK, tek liste — `_ORTAK_EK_KURALLAR` + 4 rol promptu hizalı):**
  `Swagger > Canlı Uygulama Gözlemi > Confluence > BRD/Süreç > Jira > UI`. İlke: **gözlemlenen/doğrulanabilir
  gerçek veri (Swagger sözleşmesi + MCP canlı gözlem), tarif edilen istekten (BRD) ÜSTÜNDÜR** — BRD
  hatalı/güncel-olmayan olabilir. Olgusal çelişkide (endpoint/alan/tip/gerçek davranış) gerçek veri kazanır,
  çelişki yine Açık Sorular/Tutarsızlıklar'a raporlanır. Ana doküman analizin KONUSU/izlenebilirlik çapası olarak durur.
- **Faz 2 — Ürün kalitesi:** tasarım sistemi `static/ds.css` (`ds-*`); ekranlar `screens/ciktilar.html`
  (`/api/oturum`, tazelik = mtime ≥ oturum başlangıcı), `delta.html` (Süreç'ten ayrıldı, `da-*` ID korundu),
  `yetki.html`; sidebar iş akışına göre gruplu (Analiz / Çıktılar & Revizyon / Jira / Kaynaklar / Yönetim 🔒).
  **Roller:** owner (AUTH kapalı → tek kullanıcı; açık → `ADMIN_USER`) / analist. Analist, owner'ın
  `gorunurluk.json`'da (repoda İZLENİR) gizlediği id'ler hariç her şeyi kullanır; sunucu tarafı
  `gorunurluk_kontrol` + UI `_rolUygula()`. (Denetim/audit kaydı v3'te kaldırıldı — üstteki UI v3 notuna bak.)
  Yeni gizlenebilir ekran/aksiyon → `GIZLENEBILIR_KATALOG` (app.py). **Yetki ekranı owner-KURULUM kapısı:**
  `_yetki_paneli_mi()` = `YETKI_PANELI` (yoksa `OWNER_KONSOL`) — AUTH'tan bağımsız; kendi makinesine kuran
  analist AUTH kapalıyken 'owner' olduğundan rol yetmez. `auth/me.yetki_admin` → `#nav-yetki` gösterilir;
  `/api/gorunurluk` GET/POST `yetki_gerekli` (403). Analist kurulumunda bayrak yok → ekran hiç gitmez.
  **Otomatik güncelleme (2.5):** boot'ta `_oto_guncelleme_baslat()` — iş yokken `pull --ff-only` + restart;
  dirty tree / push edilmemiş commit varsa yalnız bildirir. `.env` `AUTO_UPDATE=false` kapatır,
  `AUTO_UPDATE_INTERVAL` (sn). Banner: `screens/_guncelleme.html`. `/api/update` elle akış aynen durur.
  **2.6:** Sistem Sağlığı `/api/saglik` + `screens/saglik.html`; komut paleti ⌘K `screens/_palet.html`.
  **Faz 3 — rol-duyarlı pano + disk temizliği:** `GET /api/pano` (herkes) → Ana Sayfa "Sıradaki iş" kartları
  (`_panoIs`: bekleyen onay adımı + "Onay adımına git" · açık/kritik soru · bekleyen revizyon · çalışan iş);
  onay kapılarında **karar bağlamı** satırı (`_onayBaglamYukle` → `#onay-baglam-surec/teknik`, 15 sn throttle).
  Sağlık kartları (owner) **CLI durumu + Disk korunur**, yeni **Disk temizlik** kartı (birim boş alanı, temizlenebilir
  MB, son çalışma, zamanlama, "Şimdi temizle"). `skills/disk_temizlik.py` (0 token; `plan()` kuru / `uygula()`;
  yalnız yeniden-üretilebilir/arşiv dosyaları — `output/ input/ logs/usage/` ve referans kaynakları ASLA) +
  `_disk_temizlik_dongusu` zamanlayıcı (`DISK_TEMIZLIK=true`, `DISK_TEMIZLIK_ARALIK=86400`; iş varken erteler).
  Endpoint'ler `/api/disk/durum` (GET) · `/api/disk/temizle` (POST, meşgulse 409). Durum `logs/disk-temizlik-durum.json`.
  **Test düzeltmeleri (analist geri bildirimi):** (a) **Soru mezar-taşı** — `sorular.py` `tumunu_sil()`/`soru_sil()` silinen (id,kaynak) çiftini `data['silinen']`'e yazar; `parse_ve_birlestir` bunları kaynak dosya SİLME zamanından sonra yeniden üretilmedikçe markdown'dan GERİ EKLEMEZ (önceden 'Tümünü Sil' sonrası GET /api/sorular yeniden parse edip geri ekliyordu → 'işlem yapmıyor'). (b) **`/api/oturum` `aktif` bayrağı** — workflow idle ise FALSE; pano VE Analiz Dosyaları (ciktilar) ekranı kalıntı doküman/güncel çıktı dursa bile 'Aktif oturum yok · yüklü doküman' gösterir + 'Kaldır' (`/api/oturum/temizle`: girdi sil + `wf.sifirla`). (c) **Ayarlar CLI hesabı** — `/api/settings.cli_hesap` (`_cli_hesap_oku`, ~/.claude.json'dan e-posta/org; token OKUNMAZ) → CLI'ın hangi hesaba bağlı olduğu Ayarlar'da info. (d) **Pano Yenile** görünür geri bildirim (`panoYenile`, toast). (e) **Jira Ayarları sadeleştirme:** site adresi `jira_site_url()` ile accessible-resources'tan OTOMATİK algılanır — elle `JIRA_URL` yalnız yedek; `/api/jira/config` GET `site_url` döner, UI salt-okunur gösterir + elle giriş 'Gelişmiş' altında; `/api/jira/test` JIRA_URL'i zorunlu tutmaz. Callback URL (`/api/jira/callback`) AYRI şeydir. (h) **Görev analizi format + bağlam filtresi:** `gorev_teknik_analiz` promptu artık ana süreç→teknik analiz formatının AYNI başlık kümesini kullanır (`## 1. Amaç ve Hedefler … ## 11. Kabul Kriterleri`); görevin DOKUNDUĞU başlıklar dolu-somut yazılır, dokunulmayanlar HİÇ AÇILMAZ (boş-başlık/'yok' dolgusu yok). Çekirdek 1/3/11 + FE'de 7, DB'de 4, endpoint'te 5. **Filtre kaydı düzeltmesi:** Task Analizi bağlam filtresini OKUYOR ama ekran KAYDETMİYORDU → `jgAnaliz`/`jgCevaplariIsle` çalışmadan önce `_jgFiltreKaydet` (buildContextFilter→POST) ile ekrandaki filtreyi diske yazar (Süreç 'Başlat' deseni). NOT: `reference/` boşsa anahtar kelime ne olursa olsun RAG 0 döner — zenginlik için önce referans dokümanları senklenmeli. (g) **Task Analizi modalı — ana akış olgunluğu:** üretim/düzeltme sırasında modal-içi JARVIS reaktör (`#jg-proc`, `_jgProcBaslat/_jgProcBitir` + geçen-süre + model readout);  **İlişkili FE/BE analizi:** görevin bağlı task'ları varsa 'Teknik Analiz Et' önce SEÇİM paneli açar (`_jgSecimGoster`): birincil + bağlı task'lar, her biri katman (FE/BE, tahmin `_jgKatmanTahmin`) seçilir. 'Seçilenleri Analiz Et' her task'ı AYRI analiz eder (`jgIliskiliAnalizBaslat` → sıralı `_jgUret`), diğerleri `iliskili_keys` bağlamı olur; karşı katman yalnız `## Bağımlılık ve Arayüz (FE↔BE)` sözleşmesi olarak yazılır (backend `gorev_analiz_et(gorev, iliskili, katman)` + `gorev_getir`). Sonuçlar `_jgAnalizSeti`'te; modal üstünde task DEĞİŞTİRİCİ (`_jgSwitcherRender`/`_jgSonucGoster`), her analiz KENDİ Jira görevine ayrı yazılır. **Açık soru YAKINSAMASI (görev analizi):** `_gorev_acik_sorular_uret(teknik, gorev, cevaplar, onceki_sorular)` — takip turunda ÖNCEKİ tur soruları + analist cevapları prompt'a verilir; cevaplanan/çözülen sorular ÇIKAR, kalan açık olanlar AYNI ID+metinle korunur, yalnız cevapların doğurduğu YENİ bloklayan belirsizlik eklenir (en fazla 6). Böylece sorular turlar içinde AZALIR/biter (drift/tekrar yok). Frontend `jgCevaplariIsle` `onceki_sorular: s.acik_sorular` geçer. **Arka plan iş modeli (görev analizi GÖMÜLÜ + kesintisiz):** analiz/cevap/düzelt/formatla artık `POST /api/jira/gorev/is/baslat` ile arka plan thread'inde çalışır (`_gorev_isler`, `_gorev_is_calistir`); UI `_jgIsBaslat`→`/is/durum` polling (`_jgPollDurum`, 2.5sn). Panel MODAL değil GÖMÜLÜ (`#jg-preview-card.jg-inline`, DOMContentLoaded'da `#page-jira-gorevler`'e taşınır); kapatınca (`jgPreviewKapat`) iş DEVAM eder, üstte 'Analiz sürüyor/✓tamamlandı' çipi (`_jgSurenChipGuncelle`), ekrana dönünce `_jgReattach` (localStorage `jg-aktif-job`). 'Durdur' `/is/durdur` — **GERÇEK durdurma (madde 4):** o an süren `claude -p` süreci killpg ile ANINDA öldürülür (`base._cli_calistir` killable Popen + thread-keyed `_CLI_PROC_REG`, `cli_proc_durdur(worker_tid)`); worker `DurdurulduError`'ı iptal sayar. Yan etki: `_cli_calistir` `start_new_session=True` → claude run.py grubundan çıkar, bu yüzden run.py'ye SIGTERM/SIGINT handler eklendi (`cli_tum_durdur()` — `_surec_durdur` killpg'i claude'a bu köprüyle ulaşır). Açık sorular+cevaplar da bu gömülü panelde. **İşlem güvenliği:** üretim/yeniden-yazım/düzeltme sürerken proc başlığı task KEY gösterir; Onayla/Düzelt/Cevapları-İşle PASİF + switcher KİLİTLİ (`_jgSwitcherKilit`) + `_jgSonucGoster`/`jgJiraGuncelle` `_jgAbort` guard'ı → işlem bitmeden başka task içeriği gösterilmez ve Jira'ya YAZILMAZ. (her Q-T-XXX ayrı kart+cevap kutusu; `_jgSorulariAyristir`/`_jgSorulariRender`, yalnız dolu cevaplar `Q-T-NNN: …` olarak toplanır; ayrıştırılamazsa tek-kutu yedeği) (`#jg-cevaplar` → `jgCevaplariIsle` → `/api/jira/gorev/analiz` `cevaplar` param → analiz cevaplara göre yeniden yazılır); **iteratif düzelt** (`#jg-duzelt` → `jgAnalizDuzelt` → `/api/jira/gorev/duzelt` → `gorev_analiz_duzelt`, yalnız ilgili kısım). Sorular/cevaplar Jira'ya YAZILMAZ; Onayla yalnız analiz metnini yazar. (f) **UAT Mutabakat key link'leri:** `jira_site_url` BOŞ sonucu CACHE'LEMEZ (tek geçici hata link'leri süreç boyu kesiyordu); UI `_bsKeyLink` tabanı `_bsSonuc.jira_url || _bsJiraSite` (ekran girişinde `/api/jira/config.site_url`'den çekilir); çoklu-eşleşme önizleme key'leri de linklenir.
  **Ray görünümü (tek kolon adım akışı, geri dönüşlü):** `#surec-ray` (6 adım) / `#brd-ray` (4 adım) — `_RAY` konfig,
  `_rayInit/_rayRender/_rayTasi/_rayUygula/gorunumDegistir` (index.html). Klasik paneller `.gorunum-klasik` (DOM'da
  KORUNUR, `body.gorunum-ray` gizler); aksiyon blokları `surec-act-*`/`brd-act-*` aktif adımın `.ray-body`'sine
  TAŞINIR (kopya DEĞİL → onay/adım sohbeti/prototip sohbeti/Sadece Teknik/Durdur/Jira aynı DOM+fonksiyon). Durum
  makinesine dokunma; `_rayRender` `updateUI` sonunda + `resetWorkflowUI`'de çağrılır. "Klasik görünüm" düğmesi
  (localStorage `gorunum`) blokları orijinal panele geri taşır. Git yedeği: tag `klasik-surec-ekrani-yedek`.
  Yeni aksiyon bloğu eklersen `_RAY[p].nodes`'a da ekle; yeni workflow durumu → `_RAY[p].idx/run/turn`.
  **Faz 4 — analist-dostu hata:** `skills/hatalar.py` (`insanlastir(ham)` — 0 token, regex `_KURALLAR` sıralı:
  durduruldu/cli_limit/cli_oturum/api_key/zaman_asimi/disk/ag/mcp/model/dosya/dokuman/json/alt_surec/bilinmeyen;
  base.py import ETMEZ → run.py/workflow.py'de ucuz). `workflow.ozet()` → `hata_ozet`; UI `_hataKartiHtml`
  (başlık · ne oldu · **Ne yapmalı** · `<details>` teknik iz), toast `_hataBaslik`. Yeni hata türü → `_KURALLAR`'a
  satır ekle (ilk eşleşen kazanır; genel desenleri sona koy).
- **Test (v2):** `venv/bin/python tests/smoke_test.py` (Flask test client, deterministik uçlar) +
  `venv/bin/python tests/test_revizyon.py` + `tests/test_auth_roller.py` (AUTH açık Owner/Analist
  enforcement; env + USERS_PATH geçici) — commit öncesi ruff ile birlikte çalıştır. AI/kota harcamaz.
  Yeni deterministik endpoint → smoke_test'e bir satır ekle. Ayrıca `test_auth_roller.py`, `test_kod_kaynagi.py`.
- **Faz 3.a — Kod kaynağı:** `skills/kod_kaynagi.py` salt-okuma yerel git/dosya arayüzü (yol repo köküne
  hapsedilir; yazma/komut yok). Config `reference/kod_kaynagi.json` (gitignore + `.example` seed, seed listesinde).
  `/api/kod/*` (config owner-only) + `screens/kod.html` (Kaynaklar). Gerçek repo bağlantısı analiste bırakıldı;
  bağlı değilken analiz normal çalışır. Yeni adaptör (MCP/uzak) aynı arayüzü uygular.
- **Faz 3.b — Etki analizi:** `skills/etki_analizi.py` (çıktı varlıkları → kod isabeti) + `/api/etki/<dosya>`.
- **Faz 3.c — Retrieval + MCP:** `skills/retrieval.py` BM25 (`base._keyword_odakli_metin` içinde fallback'li;
  Türkçe-i düzeltmeli). `skills/analiz_mcp.py` Postgres/Jira MCP'yi `claude -p`'ye bağlar (config
  `reference/analiz_mcp.json` gitignore+`.example`+seed; üretilen `.mcp-analiz.json` gitignore; VARSAYILAN
  KAPALI; `_api_cagri_cli`'de canlı-app aktif değilse eklenir). `/api/analiz-mcp` owner (bağlantı maskeli).

## Komutlar
- Kurulum: `bash setup.sh` · Başlat: `./start.sh` (veya Analyst Studio.app)
- Çalışma GUI üzerinden (subprocess `run.py`); ayrı terminal test komutu yok.
- **Backend kod değişince süreç yeniden başlatılmalı** (`use_reloader=False`; sekme kapatıp açmak/sayfa yenilemek Python sürecini yeniden başlatmaz — modüller `sys.modules`'ta cache'li). UI: Güncelleme sekmesi → **"Yeniden Başlat"** (`/api/restart`, koşulsuz). "Güncelle" (`/api/update`) yalnız `git pull` yeni commit çekerse restart eder → yerelde düzenlenen dosyalarda "zaten güncel" deyip restart ETMEZ. Restart mekanizması: `_yeniden_baslat_zamanla()` (app.py) — os.execv DEĞİL (execv dinlenen socket FD'sini devralır → "Address already in use"); mevcut süreç `os._exit` ile kapanır, ayrık yeni süreç ~1.5 sn gecikmeyle aynı komutla başlar.
- Test paketi yok. **Lint: `venv/bin/ruff check .`** — commit öncesi çalıştır, TEMİZ çıkmalı (F821 gibi gerçek bug'ları yakalar; legacy stil istisnaları `ruff.toml`'da). Ayrıca app'i başlatıp boot logunu kontrol et.

## AI modu (KRİTİK — her analiz çağrısını etkiler)
Pilot ekip **CLI modu**: `.env` `USE_CLAUDE_CLI=true` (Claude.ai aboneliği, per-token yok).
CLI **görsel BRD analiz EDEMEZ** (PDF/DOCX/TXT/MD olmalı). API modu (`ANTHROPIC_API_KEY`) ikincil.

## Klasör yapısı
- `app.py` Flask sunucu (~86 endpoint) · `run.py` orchestrator (subprocess) · `workflow.py` durum makinesi · `jira_agent.py` Jira OAuth+ADF
- `skills/` iş mantığı (`agent.py` = import bridge): `base.py` (sabitler/RAG/`_api_cagri`/19 prompt), `atlassian.py` (**CANONICAL** OAuth helper), `surec_analizi` `teknik_analiz` `delta_analizi` `brd_analizi` `kapsam_analizi` `jira_tasks` `jira_gorevleri` `backlog_senkron` (**UAT Mutabakat** ekranı — UAT board'u ↔ TRADE/OPS board karşılaştırma; **0-token deterministik**; eşleştirme = mevcut Jira issue-link (UAT linki hedef-projedeki bir key'e işaret ediyorsa o hedef taranan sette olmasa bile `_keyleri_cek` ile çekilip KESİN eşleşmeye dahil edilir — "kapsam dışı hedef") + **Story köprüsü** (UAT ve hedef task AYNI Story/Hikaye'ye bağlıysa dolaylı/transitif eşleşir — `_story_baglari`: Story tipli issue-link VEYA Story tipli **parent** (alt görev doğrudan Story altında); yalnız Story seviyesi, Epic hariç. parser artık `parent_key`/`parent_type` verir) + başlık/içerik Jaccard benzerliği; sonuç UAT sıra no'suna göre artan sıralı; Epic/Story (kapsayıcı) tipler ve UAT board'unda `UAT_HARIC_DURUMLAR` durumları (şu an "Created in Error"/"Create In Error") kapsam dışı; iptal durumları (İptal Edildi/CANCEL/CANCELED — `_iptal_statusu_mu`) ana akıştan ayrılıp ayrı **İptaller** kovasında (`iptaller`) toplanır — JQL `status NOT IN` + elde güvenlik ağı; UAT **ve Hedef** task'larının **atananı** (assignee) da çıktıda (`uat_atanan`/`hedef_atanan`/`atanan`) — her iki taraf için ekranda kolon + Durum/Atanan başlık filtreleri (istemci taraflı, AND); openpyxl ile sıfırdan çok sayfalı .xlsx rapor (`UAT_Mutabakat_*`, Atanan kolonlu). Excel girişi YOK. Not: modül adı `backlog_senkron`, endpoint'ler `/api/backlog/*`, iç sayfa id `backlog-senkron` — tarihsel) `confluence_yaz` `html_mockup` (canlı uygulama Chrome MCP ile gözlemlenip tasarım dili+component'ler baz alınarak, süreç analizindeki ekranlardan çalışan prototip; **sohbetle iteratif düzeltme:** `html_mockup_duzelt(talimat)` mevcut mockup.html + talimat → güncellenmiş HTML, `/api/mockup/duzelt`+`/api/mockup/geri-al` (yedek/undo), UI'da görüntüleyicide "Sohbetle düzelt" satırı — analist istediği hâle gelene kadar düzeltir, "✓ Onayla" ile kabul eder; teknik analiz mockup.html'i kaynak alır) `sorular` `telemetri` (**Kullanım İzleme** — yalnız metadata; analiz olaylarını `logs/usage/events.jsonl`'e append eder + opsiyonel `USAGE_SINK_URL`'e fire-and-forget POST (Google Apps Script→Sheet write-only collector, bkz. `docs/telemetri-apps-script.md`); `istatistik()` 0-token deterministik özet. Emit noktaları: `run.py` (surec/teknik/brd/kapsam/jira_gonder; parent `_bekle` yalnız timeout'ta), app.py in-process endpoint'ler (mutabakat, gorev_analiz, gorev_guncelle, **mockup** `/api/mockup/generate` → olay `mockup`/"Prototip"). **Token/maliyet kaydı (P0):** her AI çağrısı `base.py`'deki süreç-geneli birikimli sayaca girdi/çıktı/cache token + maliyet ekler (CLI: JSON `usage`+`total_cost_usd`; API: `yanit.usage`, `_api_kesilme_uyar` içinden). `base.token_sayac_oku()`/`token_delta(baz)`/`_token_ekle()`. `olay_yaz(..., token={...})` → olaya `token` alanı yazılır. Emit: `run.py` sayaç=koşu toplamı (subprocess taze); app.py `_telemetri_olay(..., token_bas=_token_bas())` → delta. `istatistik()` `token_ozet` (genel) + her analistte `token{}` döndürür. API-cache replay 0 token (messages.create çağrılmaz). **KRİTİK:** `_sink_gonder` **SENKRON** POST (daemon thread DEĞİL) — `run.py` gibi kısa-ömürlü subprocess çıkışında daemon thread öldürülüp POST kayboluyordu → süreç/teknik/brd/kapsam Sheet'e HİÇ ulaşmıyordu (yalnız in-process olanlar çalışıyordu). olay_yaz işlem sonunda çağrıldığından senkron bloklama sorun değil. Jira task adedi `telemetri.jira_task_arttir()` ile hem `jira_agent.jira_task_olustur` hem `jira_tasks._issue_olustur`'dan sayılır. Analist kimliği: session username > `ANALYST_NAME` env > OS user, subprocess'e `ANALIST` env ile geçer. **Owner-gate:** `OWNER_KONSOL=true` (AUTH'tan BAĞIMSIZ — analist build'lerinde yoktur → Kullanım+Yetki sekmeleri gizli + `/api/usage/*` 403; `admin_gerekli` AUTH kapalıyken herkesi geçireceğinden ayrı bayrak ZORUNLU). **ESKİ `USAGE_DASHBOARD` bayrağı ARTIK OKUNMAZ** — analist makinelerine kopyalanan owner `.env`'i bu ekranları açıyordu; bayrak `OWNER_KONSOL`'a yenilendi ki kopyalanan eski değer işe yaramasın (analistler güncellemeyle kendiliğinden düzelir; owner `.env`'ine `OWNER_KONSOL=true` ekler). "Kullanım" sekmesi yalnız owner'da; `/api/usage/stats|pull|export`, `auth/me` artık `usage_admin` döner. **Analist kimliği UI'dan:** Ayarlar → "Analist Adı Soyadı" → `analist.json` (gitignore, makineye özel; `/api/analist` GET/POST, owner-gate YOK); analist `.env`'e dokunmaz. Sink URL koda gömülü `VARSAYILAN_SINK_URL` (yalnız-yazma; `USAGE_SINK_URL` env override eder). Kimlik önceliği: login username > `ANALIST` env > `analist.json` > `ANALYST_NAME` env > OS user. Dashboard'da **isim sıralı sabit id** (`istatistik()` analistleri casefold ile sıralayıp 1..N id verir). **Dönem bazlı** (`istatistik(gun, donem, analist)` — gun/hafta/ay trend kovası + tek-analist filtresi; `ozet` bugün/bu-hafta/bu-ay, `trend[]`, `tum_analistler`, `son_tasklar[]`). **Jira key izleme:** `jira_key_ekle()` açılan task key'lerini toplar (jira_gonder → `jira.keyler`+`islem:"acildi"`); görev güncelleme `/api/jira/gorev/guncelle` → yeni olay `gorev_guncelle` (`jira.keyler`+`islem:"guncellendi"`). Excel export'ta **Detay** sayfası (olay-bazlı, key'lerle). HTTP `requests` ile (macOS SSL için — urllib CERTIFICATE_VERIFY_FAILED veriyordu). **Çift sayım önleme:** `olaylari_oku()` — `remote.jsonl` (Sheet, owner dahil tüm ekip) VARSA yalnız onu okur (owner'ın kendi olayı hem lokal `events.jsonl` hem Sheet'te olduğundan aksi halde iki kez sayılırdı); yoksa lokal `events.jsonl`. Owner 'Uzaktan Çek' ile tazeler. Dashboard ölçümleme: **Analist Özeti** (Toplam İşlem/Başarılı/Hatalı/Açılan Task/**Toplam Süre** = efor) + **Analist × Tür matrisi** (kim hangi işi kaç kez; `analistler[].tipler`; TÜM iş tipleri sabit sütun — 0 olsa bile; Teknik Analiz [süreç→teknik] ile Görev Analizi [Jira task-bazlı] ayrı; Excel'de ayrı "Analist × Tür" sayfası) + analist seçilince **tür bazında Ort. Süre** (`analistler[].tip_sure_ms`/adet — farklı tipler ORTALANMAZ, yalnız aynı tip içinde) + legend)). **Not:** `surec_analizi` çıktı formatı analiz ekibinin Confluence şablonudur (AMAÇ/MOCKUP/GEREKSİNİMLER→Ekranlar/ÖNERİLEN DB ALANLARI/GELİŞTİRME NOTLARI); ID'ler + `| Q-001 |` tablosu + `### Süreç Adımları` başlığı pipeline çapası olarak korunur (bkz. docs/MIMARI.md).
- `templates/index.html` SPA · `reference/` RAG kaynakları (Atlassian sync) · `output/ input/ history/ logs/` runtime · `backlog/` UAT Mutabakat üretilen .xlsx raporları (gitignore) · `docs/` detaylı referans
- **Bağımlılıklar** (`requirements.txt`): Flask, anthropic, requests, python-dotenv, PyMuPDF, Pillow, python-docx, ruff + **openpyxl** (UAT Mutabakat .xlsx rapor yazımı). `lxml` hâlâ kurulu (genel kullanım).
- `reference/live-app` Claude MCP/Chrome ekran+network gözlem çıktıları içindir (gitignore); bağlam filtresinde ana URL + 5 alt URL ve "Örnek ekran olarak kullan" seçeneği süreç/teknik analize canlı uygulama görevi olarak eklenir.
- **Canlı uygulama ÇALIŞMASI için `claude -p`'ye MCP + izin geçmek ZORUNLU** — bkz. `docs/MIMARI.md` "Canlı Uygulama (Chrome MCP)". `--allowedTools` verilmezse headless modda tarayıcı araçları sessizce reddedilir.
  **Sağlamlaştırma (Faz 7):** (a) `@playwright/mcp` **sürüm PİNLİ** (`@0.0.80`, `@latest` DEĞİL — araç-adı kırılmalarına karşı). (b) **Sessiz-düşüş tespiti:** canlı gözlem istendi ama `permission_denials`'ta browser reddi veya `num_turns<=1` (hiç araç kullanılmadı) ise `_api_cagri_cli` net uyarı loglar + subprocess çıktısına yazar (analist app log'unda görür). (c) **Şifre redaksiyonu:** `_canli_app_sifre_redakte` yapılandırılmış giriş şifresini çıktıdan deterministik temizler (prompt kuralına ek). (d) Odaklı gözlem modu (`gozlem_kapsami`) artık `use_as_sample` örnek-ekran notunu da içerir. (e) `/api/live-app/status` `hazir` = npx+url+profil **+ CLI modu + claude CLI** (yalnız CLI yolunda çalışır); `cli_modu`/`claude_var` alanları eklendi. Kalan öneriler (düşük öncelik): TimeoutExpired için dostça mesaj, live-app cache bypass, iki akışın profil serileştirmesi.

## Hard kurallar
1. **Türkçe** yaz (print/yorum/hata); teknik terimler İngilizce kalır.
2. Asla commit etme: `.env` (chmod 600) + makineye özel `reference/{context_filter,prompts,sources}.json` (gitignore'da; `*.json.example` izlenir, açılışta `_runtime_config_seed()` ile seed).
3. Atlassian helper → her zaman `skills/atlassian.py`'den import (duplicate tanım yok).
4. Yeni output dosyası → `IZIN_VERILEN_CIKTILAR` (app.py). Yeni Jira field → `jira_agent.py` + `skills/jira_tasks.py`.
5. Prompt önceliği: ekrandaki **Özel Prompt** (`context_filter.json → ozel_prompt`, analiz-bazlı, varsayılanın YERİNE geçer) > `reference/prompts.json` (kalıcı override) > `VARSAYILAN_PROMPTLAR` (base.py).
6. `sys.executable` kullan, Python yolu hard-code etme. `env_oku()` tırnakları strip eder.
7. **GÜVENLİK: canlı-uygulama parolası** (`context_filter.json` `live_app_auth.password`) `GET /api/context-filter`'da TARAYICIYA GÖNDERİLMEZ — maskeli (`has_password` bool). POST'ta boş parola gelirse mevcut KORUNUR (maskeli UI silmesin); `sifre_temizle:true` açıkça boşaltır. Diskte 0600+gitignore. Tam keychain: P1.

## İlgili dosyalar — TÜM REPOYU TARAMA
Görev başında geniş dizinleri (`reference/`, `venv/`, `logs/`, `output/`) tarama. İhtiyaca göre:
- Mimari / sabitler / RAG / promptlar / workflow / 3-aşamalı teknik analiz / Jira Görevleri / cache / TL;DR → **`docs/MIMARI.md`**
- Tam endpoint kataloğu (~80) → **`docs/ENDPOINTS.md`**
- Auth / CSRF / güvenlik / dağıtım / onboarding → **`docs/GUVENLIK-DAGITIM.md`**
- Faz / değişiklik geçmişi → **`docs/DEGISIKLIK-GECMISI.md`**
- Belirli iş mantığı → ilgili tek `skills/<modül>.py` (önce o dosyayı oku, base.py'yi sadece gerekirse).

## CLAUDE.md / docs bakımı (zorunlu)
Dosya yapısı, skill sorumluluğu, endpoint, sabit/limit/model, prompt, workflow veya hard kural değişince
ilgili `docs/*` + bu özeti aynı/takip commit'inde güncelle. Sadece CSS/typo atlanabilir.
`.claude/hooks/post-commit-reminder.py` hatırlatır; nihai sorumluluk Claude'da.
