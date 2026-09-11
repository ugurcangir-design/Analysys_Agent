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
  Sağlık kartları (owner): **Sürüm · AI/Kota · Güncelleme · İş akışı** (sadeleştirildi). **NOT (UI sadeleştirme):**
  "Veri kaynakları", "Disk" ve "Disk temizlik" kartları panodan KALDIRILDI (analiste gereksiz sistem gürültüsü;
  lokal disk kapasitesi göstermeye gerek yok, loglar Güncelleme ekranında; disk temizliği arka planda otomatik).
  **Backend duruyor (sessiz bakım):** `skills/disk_temizlik.py` (0 token; `plan()` kuru / `uygula()`;
  yalnız yeniden-üretilebilir/arşiv dosyaları — `output/ input/ logs/usage/` ve referans kaynakları ASLA) +
  `_disk_temizlik_dongusu` zamanlayıcı (`DISK_TEMIZLIK=true`, `DISK_TEMIZLIK_ARALIK=86400`; iş varken erteler).
  Endpoint'ler `/api/disk/durum` (GET) · `/api/disk/temizle` (POST, meşgulse 409) — artık UI'dan çağrılmıyor. Durum `logs/disk-temizlik-durum.json`.
  **Task Analizi / test düzeltmeleri (özet):** görev analizi akışı — JARVIS reaktör, ilişkili FE/BE **seçim paneli** (`_jgSecimGoster`), **gömülü** panel (`#jg-preview-card.jg-inline`), arka plan iş (`_gorev_is_calistir`) + **paralel** (ThreadPoolExecutor, `GOREV_PARALEL`), açık soru **yakınsaması** (`_gorev_acik_sorular_uret onceki_sorular`), **gerçek Durdur** (killpg). Ayrıca: soru mezar-taşı, `/api/oturum` `aktif` bayrağı, CLI hesabı bilgisi, Jira Ayarları sadeleştirme (site otomatik), UAT key link'leri, bağlam-filtresi kaydı (`_jgFiltreKaydet`). **Tam akış + tüm alt-düzeltmeler → `docs/MIMARI.md` "Task Analizi" + `docs/DEGISIKLIK-ARSIV.md`.**
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
  Yeni deterministik endpoint → smoke_test'e bir satır ekle. Ayrıca `test_auth_roller.py`, `test_kod_kaynagi.py`,
  `test_jira_kopru.py` (Jira Köprüsü komut→taslak→onay durum makinesi, offline/0-token).
- **Faz 3.a — Kod kaynağı:** `skills/kod_kaynagi.py` salt-okuma yerel git/dosya arayüzü (yol repo köküne
  hapsedilir; yazma/komut yok). Config `reference/kod_kaynagi.json` (gitignore + `.example` seed, seed listesinde).
  `/api/kod/*` (config owner-only) + `screens/kod.html` (Kaynaklar). Gerçek repo bağlantısı analiste bırakıldı;
  bağlı değilken analiz normal çalışır. Yeni adaptör (MCP/uzak) aynı arayüzü uygular.
- **Faz 3.b — Etki analizi:** `skills/etki_analizi.py` (çıktı varlıkları → kod isabeti) + `/api/etki/<dosya>`.
- **Faz 3.c — Retrieval + MCP:** `skills/retrieval.py` BM25 (`base._keyword_odakli_metin` içinde fallback'li;
  Türkçe-i düzeltmeli). `skills/analiz_mcp.py` Postgres/Jira MCP'yi `claude -p`'ye bağlar (config
  `reference/analiz_mcp.json` gitignore+`.example`+seed; üretilen `.mcp-analiz.json` gitignore; VARSAYILAN
  KAPALI; `_api_cagri_cli`'de canlı-app aktif değilse eklenir). `/api/analiz-mcp` owner (bağlantı maskeli).
- **Jira Köprüsü (Jira'yı web-chat gibi kullan):** `skills/jira_kopru.py` + `_jira_kopru_dongusu` (app.py).
  Analist bir Jira task'ının YORUMUNA `/analyst_agent <komut>` yazar → app **polling** (JQL taraması,
  inbound/webhook YOK — lokal + OAuth) ile bulur, işler, sonucu Jira **yorumu** olarak geri yazar
  (`jira_yorum_ekle`, canonical `atlassian_post` + `markdown_to_adf`). **Varsayılan KAPALI**
  (`JIRA_KOPRU=false`; owner açar), owner-gate `/api/jira-kopru/durum|tara`.
  **Komutlar:** `analiz [talimat]` → `gorev_getir`+`gorev_analiz_et`, sonucu yorum (okuma, oto; çıktı
  `son_analiz` önbelleğine — `güncelle`/`ilişkili-aç` `_ANALIZ_TAZE_DK`=60dk içinde yeniden analiz etmez) ·
  `güncelle` → analizi task açıklamasına yazmayı **önerir (taslak)** · `ilişkili-aç` → analizden ilişkili
  YENİ task'lar **önerir (taslak)** (`_iliskili_task_onerileri` AI, ≤`_MAX_ILISKILI`=5) · `onayla` → bekleyen
  taslağı UYGULAR (güncelle→`gorev_jiraya_yaz`; ilişkili-aç→`_issue_olustur` + `jira_issue_link` Relates,
  kaynakla aynı projede) · `iptal`/`yardım`. **Güvenlik/korkuluk:** yorum=KOMUT (talimat değil; analiz girdisi
  task'ın kendi içeriği) · geri-döndürülemez yazma YALNIZ `onayla` sonrası (taslak+onay, human-in-the-loop) ·
  çift-uygulama önlemi (onayla taslağı hemen düşürür) · döngü koruması (kendi `🤖` yanıtı komut prefiksiyle
  başlamaz + işlenen yorum id'leri `output/jira-kopru/durum.json`) · opsiyonel `JIRA_KOPRU_YAZAR_ALLOWLIST`.
  Env: `JIRA_KOPRU_PROJELER` (zorunlu) / `_ARALIK` / `_PENCERE_DK` / `_KOMUT`. Test: `tests/test_jira_kopru.py`
  (offline durum-makinesi, 0 token). Tam uç dökümü → `docs/ENDPOINTS.md` "Jira Köprüsü".

## Komutlar
- Kurulum: `bash setup.sh` · Başlat: `./start.sh` (veya Analyst Studio.app)
- Çalışma GUI üzerinden (subprocess `run.py`); ayrı terminal test komutu yok.
- **Backend kod değişince süreç yeniden başlatılmalı** (`use_reloader=False`; sekme kapatıp açmak/sayfa yenilemek Python sürecini yeniden başlatmaz — modüller `sys.modules`'ta cache'li). UI: Güncelleme sekmesi → **"Yeniden Başlat"** (`/api/restart`, koşulsuz). "Güncelle" (`/api/update`) yalnız `git pull` yeni commit çekerse restart eder → yerelde düzenlenen dosyalarda "zaten güncel" deyip restart ETMEZ. Restart mekanizması: `_yeniden_baslat_zamanla()` (app.py) — os.execv DEĞİL (execv dinlenen socket FD'sini devralır → "Address already in use"); mevcut süreç `os._exit` ile kapanır, ayrık yeni süreç ~1.5 sn gecikmeyle aynı komutla başlar.
- Test paketi yok. **Lint: `venv/bin/ruff check .`** — commit öncesi çalıştır, TEMİZ çıkmalı (F821 gibi gerçek bug'ları yakalar; legacy stil istisnaları `ruff.toml`'da). Ayrıca app'i başlatıp boot logunu kontrol et.

## AI modu (KRİTİK — her analiz çağrısını etkiler)
Pilot ekip **CLI modu**: `.env` `USE_CLAUDE_CLI=true` (Claude.ai aboneliği, per-token yok).
CLI **görsel BRD analiz EDEMEZ** (PDF/DOCX/TXT/MD olmalı). API modu (`ANTHROPIC_API_KEY`) ikincil.
**429 dayanıklılığı (P1-B):** CLI kullanım limiti (429) `base.CliLimitError` fırlatır; `_api_cagri` bunu
yakalar ve **ANTHROPIC_API_KEY varsa** o çağrıyı otomatik API moduyla tamamlar (analistin işi kesilmez).
Anahtar yoksa (analist CLI makinesi) net hata yükselir. `CLI_LIMIT_API_FALLBACK=false` ile kapatılır
(maliyet kontrolü). `_api_cagri_direct` CLI modunda `anthropic`'i tembel import eder. Limit durumu +
sıfırlanma saati `/api/cli/durum` header göstergesinde görünür (`cli_durum_oku`).

## Klasör yapısı
- `app.py` Flask sunucu (~86 endpoint) · `run.py` orchestrator (subprocess) · `workflow.py` durum makinesi · `jira_agent.py` Jira OAuth+ADF
- `skills/` iş mantığı (`agent.py` = import bridge): `base.py` (sabitler/RAG/`_api_cagri`/promptlar), `atlassian.py` (**CANONICAL** OAuth helper), `surec_analizi` `teknik_analiz` `delta_analizi` `brd_analizi` `kapsam_analizi` `jira_tasks` `jira_gorevleri` `backlog_senkron` (**UAT Mutabakat** — 0-token deterministik) `confluence_yaz` `html_mockup` (canlı-app baz'lı prototip + sohbetle düzeltme) `sorular` `telemetri` (**Kullanım İzleme** + token/maliyet kaydı; owner-gate **`OWNER_KONSOL`**; `_sink_gonder` SENKRON; çift-sayım önleme `remote.jsonl`) `hatalar` `disk_temizlik` `jira_kopru` (**Jira Köprüsü** — Jira'yı web-chat gibi kullan; aşağı bak) `kod_kaynagi` `etki_analizi` `retrieval` `analiz_mcp`. **Modül sorumlulukları + telemetri/backlog/mockup tam ayrıntı → `docs/MIMARI.md`.**
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
7. **GÜVENLİK: canlı-uygulama parolası** (`context_filter.json` `live_app_auth.password`) `GET /api/context-filter`'da TARAYICIYA GÖNDERİLMEZ — maskeli (`has_password` bool). POST'ta boş parola gelirse mevcut KORUNUR (maskeli UI silmesin); `sifre_temizle:true` açıkça boşaltır. Diskte 0600+gitignore. **Sır redaksiyonu (P1-D):** `base.sir_kaydet/sir_redakte` + `app._SirRedaksiyonFiltre` tüm loglardan API anahtarı/şifre/`sk-…` desenlerini «sır» ile maskeler; açılışta `_hassas_dosya_izinlerini_sertlestir` `.env`+`context_filter.json`'ı 0600 yapar. API anahtarı kullanıcı tercihiyle düz metin kalır (keychain uygulanmadı — bilinçli).

## İlgili dosyalar — TÜM REPOYU TARAMA
Görev başında geniş dizinleri (`reference/`, `venv/`, `logs/`, `output/`) tarama. İhtiyaca göre:
- Mimari / sabitler / RAG / promptlar / workflow / 3-aşamalı teknik analiz / Jira Görevleri / **Task Analizi akış detayı** / **telemetri + skills modül sorumlulukları (tam metin)** / cache / TL;DR → **`docs/MIMARI.md`**
- Tam endpoint kataloğu (~80) → **`docs/ENDPOINTS.md`**
- Auth / CSRF / güvenlik / dağıtım / onboarding → **`docs/GUVENLIK-DAGITIM.md`**
- Faz / değişiklik geçmişi → **`docs/DEGISIKLIK-GECMISI.md`** (özet index + son işler); eski işlerin tam metni → **`docs/DEGISIKLIK-ARSIV.md`**
- Belirli iş mantığı → ilgili tek `skills/<modül>.py` (önce o dosyayı oku, base.py'yi sadece gerekirse).

## CLAUDE.md / docs bakımı (zorunlu)
Dosya yapısı, skill sorumluluğu, endpoint, sabit/limit/model, prompt, workflow veya hard kural değişince
ilgili `docs/*` + bu özeti aynı/takip commit'inde güncelle. Sadece CSS/typo atlanabilir.
`.claude/hooks/post-commit-reminder.py` hatırlatır; nihai sorumluluk Claude'da.
