# Değişiklik Geçmişi / Tamamlanan İşler (referans)

> Ana referans: [CLAUDE.md](../CLAUDE.md). Bu dosya **son/devam eden işleri tam metinle** +
> daha eski tamamlanmış faz ve düzeltmelerin **özet index'ini** tutar. Eski işlerin TAM
> açıklamaları → [DEGISIKLIK-ARSIV.md](DEGISIKLIK-ARSIV.md).
> Büyük bir faz/özellik tamamlandığında buraya özet ekle; olgunlaşınca (yeni işler üstüne
> geldikçe) detayı arşive taşıyıp burada index satırına indir.

## P1 iyileştirmeler — devam ediyor
- **A — Token/maliyet paneli** ✅: Kullanım Raporu artık madde 2'de toplanan token verisini gösterir.
  `#ku-ozet`'e **Token / Maliyet** kart grubu (girdi/çıktı/cache okuma token + tahmini maliyet USD;
  yalnız veri varsa görünür); analist özet tablosuna **Token** (girdi+çıktı, tooltip'te kırılım) +
  **Maliyet** sütunları (yoksa '·'). Excel export'ta Analist Özeti sayfasına 4 token sütunu eklendi.
  Deterministik (0 token). CLI abonelik modunda maliyet bilgilendirme amaçlıdır.
- **B — CLI limit (429) dayanıklılığı** ✅: CLI kullanım limiti artık `base.CliLimitError` (reset alanlı)
  fırlatır. `_api_cagri` bunu yakalar → **ANTHROPIC_API_KEY varsa** çağrıyı otomatik API moduyla tamamlar
  (analistin işi kesilmez); anahtar yoksa net hata yükselir. `CLI_LIMIT_API_FALLBACK=false` ile kapatılır.
  `_api_cagri_direct` CLI modunda `anthropic`'i tembel import eder (modül düzeyinde import edilmiyordu).
  Limit + sıfırlanma saati zaten `/api/cli/durum` header göstergesinde. `api_cagri_kapanisli` `_api_cagri`
  üzerinden fallback'i devralır.
- **C — Görev analizini paralelleştir** ✅: çok adımlı görev analizi işleri (ilişkili FE/BE task'ları,
  "Sadece Client" grubu) artık `ThreadPoolExecutor` ile **eşzamanlı** çalışır (tavan `GOREV_PARALEL`=3;
  1 → seri fallback). 3 task ≈ 3× hız. **Madde 2 ile uyum:** global-sayaç delta'sı paralelde yanlış
  olurdu → `base.token_capture_baslat/al` **thread-local** capture eklendi (her adım kendi token'ını
  doğru ölçer; global sayaç yine tüm-süreç toplamını tutar, run.py için). `_telemetri_olay` artık
  thread-local capture kullanır. **Madde 4 ile uyum:** Durdur tek `worker_tid` yerine `job["worker_tids"]`
  kümesindeki TÜM pool thread'lerini killpg eder. iptal kontrolü submit öncesi + adım başında.
- **D — Güvenlik sertleştirme** ✅: (a) **Sır redaksiyonu:** `base.sir_kaydet/sir_redakte` +
  `app._SirRedaksiyonFiltre` → tüm log kayıtlarından ANTHROPIC_API_KEY, canlı-app şifresi ve anahtar
  desenleri (`sk-ant-…`/`sk-…`) «sır» ile maskelenir. Sırlar açılışta (`_sirlari_yukle`) + şifre değişince
  (`context_filter_kaydet`) kaydedilir. (b) **Dosya izni:** açılışta `_hassas_dosya_izinlerini_sertlestir`
  `.env` + `context_filter.json`'ı 0600'e sıkılaştırır (gevşekse). (c) **API anahtarı:** kullanıcı
  tercihiyle düz metin kalır (keychain/şifreleme bilinçli olarak uygulanmadı); redaksiyon+izin+gitignore
  ile korunur. Test: literal+desen redaksiyon, logging filtresi uçtan uca, izin sıkılaştırma doğrulandı.

## P0 iyileştirmeler (token/güvenlik/durdurma) — devam ediyor
- **Madde 1 — canlı-uygulama şifre maskeleme** ✅ (`f326daa`): `GET /api/context-filter` şifreyi
  tarayıcıya göndermez (`has_password` bool + username); `POST` şifreyi korur/temizler (`sifre_temizle`).
- **Madde 2 — token/maliyet kaydı** ✅: her AI çağrısı `skills/base.py`'deki süreç-geneli birikimli
  sayaca girdi/çıktı/cache token + maliyet ekler (CLI: JSON `usage`+`total_cost_usd`; API: `yanit.usage`,
  `_api_kesilme_uyar` içinden). API: `token_sayac_oku()`/`token_delta(baz)`/`_token_ekle()`. `telemetri.olay_yaz`
  yeni `token` alanı alır → `events.jsonl`/Sheet'e yazılır. Emit noktaları: `run.py` (subprocess taze → sayaç=koşu
  toplamı), app.py in-process (`_telemetri_olay(..., token_bas=_token_bas())` → delta). `telemetri.istatistik`
  artık `token_ozet` (genel) + her analistte `token{}` döndürür (0-token deterministik özet). Gelecek maliyet
  dashboard'ının temeli.
- **Madde 3 — getirim bütçesi + prompt-cache genişletme** ✅: (a) `MAX_CHARS_REF_GLOBAL`
  (`.env`, varsayılan 140000) — tüm referans tiplerinin TOPLAMI için tavan. Per-tip limitler tek
  başına 280K karakter (~70K token) getirebiliyordu; `_ref_bloklari_olustur` artık tipleri sırayla
  (Confluence→Jira→Servis→Canlı→Diğer) global bütçe dolana dek doldurur, sonra keser (0/negatif →
  sınırsız, eski davranış). (b) Görev analizinde ikinci cache breakpoint: görev içeriği (key/başlık/
  açıklama + analist notu) cevap/düzeltme turları arasında değişmez → refs breakpoint'ine ek olarak
  görev bloğuna da `cache_control` konur; cevap turlarında görev içeriği cache'ten okunur (sistem+refs+
  görev = 3 breakpoint, Anthropic tavanı 4). CLI modu cache_control'ü yok sayar (API modu kazanır).
- **Madde 4 — gerçek "Durdur" (görev analizi hard-kill)** ✅: görev analizi arka plan thread'inde
  çalışıyor; içindeki `claude -p` çağrısı önceden bloklu `subprocess.run`'dı → 'Durdur' bayrağı konsa da
  süren AI çağrısı token yakarak tamamlanana dek sürüyordu. Artık `base._cli_calistir` killable Popen
  (`start_new_session=True` → torunlarla ayrı grup) + thread-keyed registry (`_CLI_PROC_REG`);
  `cli_proc_durdur(tid)` o worker'ın CLI sürecini killpg eder. `/api/jira/gorev/is/durdur` worker
  thread ident'i üzerinden ANINDA öldürür (`cli_oldurdu` döner); worker `DurdurulduError`'ı iptal olarak
  işler (hata değil). **Regresyon önlemi:** `start_new_session` claude'u run.py grubundan çıkardığından
  `_surec_durdur`'un killpg(run.py)'ı artık claude'a ulaşmaz → run.py'ye SIGTERM/SIGINT handler eklendi,
  `cli_tum_durdur()` ile kendi claude çocuğunu öldürüp çıkar (entegrasyon testiyle doğrulandı). API modu:
  HTTP çağrısı kesilemez, iptal bayrağı sonraki adımları durdurur.

## UI v3 — yeniden tasarım + ekran/menü düzeni (YALNIZ v2) ✅
- **Görsel dil:** slate + indigo palet (koyu/açık tema), Space Grotesk başlık, yüksek kontrast, 10px köşe;
  token tabanlı (`:root`/`[data-theme]`) → tüm ekranlara yansır. Renk anlamı: kırmızı=çalışan işlem,
  amber=analist onayı, yeşil=başarı, indigo=marka.
- **İşlem göstergeleri:** üst barda kalıcı işlem çipi (`#run-chip`, her ekran) + tam-ekran İşlem Modu HUD
  (`#islem-modu`, JARVIS tarzı kırmızı reaktör; kapatınca iş arka planda sürer).
- **Menü/ekran:** açılır-kapanır sol menü + katlanır grup başlıkları; kart tabanlı Ana Sayfa (`pano.html`);
  sol altta analist adı/rolü (`/api/analist`) + üst-bar avatarı; Kılavuz menüden alındı, üst-bar **?** düğmesi açar;
  sağ-üst Ayarlar düğmesi kaldırıldı.
- **Yeniden adlandırma:** Jira Görevleri → **Task Analizi** (iç anahtar `jira-gorevler` korundu), Kullanım →
  **Kullanım Raporu**, Yetki & Denetim → **Yetki**.
- **Denetim (audit) KALDIRILDI:** `skills/denetim.py`, `/api/denetim`, `logs/audit.jsonl`, `_denetim()` emitleri,
  `/api/saglik` `denetim{}`, Yetki'deki Denetim paneli — hepsi çıkarıldı. Analist iş takibi tamamen Kullanım Raporu
  (telemetri). Testler güncellendi (smoke 27, auth/rol 20).

## Kullanım İzleme (Telemetri) ✅
- **`skills/telemetri.py`** — analiz olaylarını yalnız metadata olarak loglar (analist, olay tipi,
  durum, süre, model, AI modu, açılan Jira task adedi, bağlam proje/doküman). Doküman içeriği ASLA.
  Lokal `logs/usage/events.jsonl` (append-only) + opsiyonel `USAGE_SINK_URL`'e fire-and-forget POST.
  `istatistik()` = 0-token deterministik özet (analist × tür × zaman, başarı, süre, task).
- **Transport:** Google Apps Script → özel Sheet, **write-only** (analistler yazar, okuyamaz). Owner
  `USAGE_SINK_KEY` ile "Uzaktan Çek" (`/api/usage/pull`). Kurulum: `docs/telemetri-apps-script.md`.
- **Owner-gate:** `OWNER_KONSOL=true` (eski adı `USAGE_DASHBOARD`; bkz. arşiv) — AUTH'tan bağımsız; yalnız
  owner `.env`'inde. Analist build'lerinde yok → sekme gizli + `/api/usage/*` 403. `auth/me` → `usage_admin`.
- **Emit noktaları:** `run.py` (surec/teknik/brd/kapsam/jira_gonder; parent yalnız timeout), app.py
  in-process (mutabakat, gorev_analiz). Jira sayımı iki oluşturma yolundan da toplanır. Analist
  kimliği subprocess'e `ANALIST` env ile geçer. Endpoint: `/api/usage/stats|pull|export`; UI:
  owner-only "Kullanım Raporu" sekmesi (özet kartlar + analist tablosu + tür kırılımı + Excel).

---

## Kilometre taşları ve düzeltmeler — özet index
> Tam açıklamalar: **[DEGISIKLIK-ARSIV.md](DEGISIKLIK-ARSIV.md)** (aynı başlıklarla, tarihsel sıra).
> Aşağıdaki satırlar hepsi **✅ tamamlandı** (ruff temiz + doğrulanmış); detay için arşive bak.

### Fazlar (mimari kilometre taşları)
- **Faz 1 — Skill ayrıştırma:** `agent.py` → import bridge; iş mantığı `skills/` altında.
- **Faz 2:** Confluence yazma, Jira hiyerarşi (FE/BE), API Şema & DDL, HTML Prototip.
- **Faz 3:** atlassian dedup, RAG tüm analizlerde, Jira JSON→kompakt md, tip-bazlı ref, FE/BE ayrımı,
  15 promptun yeniden yazımı, yeni ID tipleri, stabilite (log rotation/retry/crash recovery), GitHub self-update.
- **Faz 4 — Teknik analiz kalite + Jira Görevleri:** üç aşamalı teknik analiz, çıktı kesilme koruması,
  Jira Görevleri sekmesi (triyaj/sınıflandırma/yorum/formatla/analiz et), `markdown_to_adf` RAG-yorum temizliği.
- **Faz 5 — Backlog Senkron + Jira Görevleri iyileştirmeleri:** deterministik UAT→TRADE/OPS takip Excel'i
  (cerrahi lxml zip), "Tüm Görevler"+statü filtresi, Analist Notu, "Sadece Client", export, bulkfetch tazelik,
  görev-bazlı yalın teknik analiz, canlı gözlem MCP ekonomisi, WCAG AA, CLI 401 OAuth teşhisi.
- **Faz 6 — Backlog → Backlog Mutabakat:** board-to-board mutabakat (`mutabakat()` 0 token; KESİN/YÜKSEK/
  ADAY/EŞLEŞMEYEN katmanları), openpyxl çok-sayfalı rapor, `_jira_site_url()`, yeni UI; gerçek veriyle doğrulandı.
- **Faz 7 — UAT Mutabakat:** ekran adı "UAT Mutabakat", UAT sıra no + sıralı liste, stat-kartı filtre, rozetler.
- **Faz 8 — Süreç Analizi Confluence şablonu + HTML Prototip canlı-uygulama baz'ı:** ekran-merkezli şablon
  (AMAÇ→MOCKUP→GEREKSİNİMLER→DB→NOTLAR, ID'ler gömülü), mockup canlı-app URL'inden tasarım dili alır.
- **Faz 9 — Süreç analizi RAG düzeltmesi + İlişkili/Etki:** PDF filtre bug'ı (`_filtre_metni_oku`),
  baştan-kesme (`_keyword_odakli_metin`), İlişkili/Etki (IB-XXX) bölümü, Confluence 404 token-yenileme bug'ı.
- **Faz 2 (revizyon iş akışı) — Adım sohbeti + geri dönüş + hedefli soru:** `/api/adim/duzelt` (hedefli bölüm
  düzenleme + oto-onay), `/api/geri-don` (TEKNIK_ONAY→ONAY_BEKLENIYOR), `_sorulari_hedefli_uygula`.
- **Faz 3 (ürün) — Rol-duyarlı pano + onay bağlamı + disk temizliği:** `/api/pano` "Sıradaki iş" kartları,
  onay kartı karar bağlamı, `skills/disk_temizlik.py` + zamanlayıcı (yalnız yeniden-üretilebilir dosyalar).
- **Faz 4 (ürün) — Analist-dostu hata mesajları:** `skills/hatalar.py insanlastir` (regex → başlık/ne oldu/
  ne yapmalı/teknik iz), `workflow.ozet().hata_ozet`, UI hata kartı + toast.
- **Ray görünümü:** Süreç/Teknik (6 adım) ve BRD (4 adım) tek-kolon adım akışı; klasik paneller DOM'da korunur
  (`.gorunum-klasik`), aksiyon blokları aktif adıma TAŞINIR (kopya değil); "Klasik görünüm" ile geri; tag `klasik-surec-ekrani-yedek`.

### UAT Mutabakat — artımlı düzeltmeler
- Durum kolonu hızlı filtresi (istemci-taraflı, AND).
- "Create In Error" / "Created in Error" varyantları UAT kapsam dışı (`UAT_HARIC_DURUMLAR` + casefold ağı).
- Durum filtresi: kapsam-dışı seçenek temizliği + dropdown UX/görsel (caret, huni, `.is-aktif`).
- Atanan (assignee) kolonu + filtre (UAT + Hedef TRADE/OPS), generic `_bsFiltreTh`, "(Atanmamış)" sentinel.
- İptal kovası + Epic/Story eleme (`_kapsayici_tip_mi`, `_iptal_ayir`); İptal Edildi stat kartı + Excel sayfası.
- KESİN eşleşme gerekçesi: ilişki/bağlılık türü + yön (`_iliski_sinifi`).
- Kapsam dışı ama linkli hedef task'lar eşleşmede (bug fix; `link_hedef_index`).
- Story köprüsü (transitif eşleşme) — ortak Story üzerinden dolaylı; sonra PARENT (alt görev) bağını da kapsar.
- Story köprüsü YANLIŞ POZİTİF düzeltmesi (kritik): köprü yalnız **hedef board story'leri** üzerinden.
- "Epic/Story altı" modu ÖZYİNELEMELİ (BFS, tüm alt-ağaç).
- İptal board bazlı + hedef "Story" kolonu (proje filtresi, Excel sütunları).
- Jira task key link'leri geri geldi (boş `jira_site_url` cache'leme bug'ı + `_bsKeyLink` yedek).
- Bir UAT → çok hedef: özet satır + tıkla-genişlet; distinct UAT sayımı; Excel "UAT İş Adedi".

### CLI / model / hata mesajları
- CLI 429 mesajı: "session limit" (5 saatlik pencere) vs genel kota netleştirmesi → sonra tek-sebep iddiasını
  bırakıp Claude Code `/status`·`/usage`'a yönlendirme.
- CLI modeli Fable olmasın: `--model` DAİMA açık geçilir (`CLAUDE_CLI_MODEL`, vars. `sonnet`); Jira analizi
  AbortController ile iptal edilebilir.
- Header'da canlı **CLI limit göstergesi** (`cli_durum_oku/probe`, `output/cli-usage-state.json`, `/api/cli-usage`).

### Süreç/Teknik + Task Analizi + uygulama düzeltmeleri
- Güvenilir "Yeniden Başlat": `/api/restart` + os.execv restart bug'ı (socket FD devri) → `os._exit`+ayrık süreç.
- "Sadece Teknik Analiz" yeni yüklenen dokümanı kaçırıyordu (mtime karşılaştırması).
- Takılı "Hata oluştu" + tekrar eden hata toast'u (workflow sıfırla + yalnız geçişte toast).
- Header durum göstergesi sekmeye göre güncellenir (stale JG mesajı sızmıyor).
- Görev teknik analizi promptu: çözüm-odaklı (gözlem→çözüm) → başlıklar ekip formatına geri alındı →
  ana 11-başlık formatına hizalandı (dokunulan başlık dolu, dokunulmayan hiç açılmaz).
- Swagger fetch gerçek OpenAPI spec'i çözer (`_swagger_spec_cek`, aynı-host önceliği, petstore elenir);
  "mevcut yeteneği yeni iş sanma" kuralı.
- Test geri bildirimi 4 düzeltme: Tümünü Sil mezar-taşı, CLI hesap info, Pano Yenile geri bildirim, kalıntı doküman
  "aktif oturum" (`/api/oturum.aktif` + `/api/oturum/temizle`) — pano + Analiz Dosyaları.
- Jira Ayarları sadeleştirme: site adresi otomatik algılanır (callback ≠ site URL).
- Task Analizi olgunlaştırma: modalı ana akış (JARVIS + cevaplanabilir sorular + iteratif düzelt) → soru-bazlı
  cevap girişi → ilişkili FE/BE (iki ayrı analiz + task switcher + katman sözleşmesi) → işlem-sürerken güvenlik
  (kilit/guard) → arka plan iş modeli + gömülü panel (kapatınca kesilmez) → açık soru YAKINSAMASI (drift önlemi).
- Owner konsol bayrağı yenilendi: `USAGE_DASHBOARD` → **`OWNER_KONSOL`** (kopyalanmış eski bayrak ekranı açmaz).
