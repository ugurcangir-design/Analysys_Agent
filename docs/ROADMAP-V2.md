# Analyst Studio v2 — Yol Haritası

> **Çapa doküman.** Bu plan v2 inisiyatifinin kalıcı çapasıdır. Her yeni context bu
> dosyayı okuyup hizalanır. Kaynak artifact: `f67b7279-5df5-4d92-9d45-5ad7d59e54fc`
> (Strateji & Yol Haritası · Eylül 2026).

**Amaç:** Süreç, BRD ve teknik analiz ekranlarını gerçek bir uygulama kalitesine
taşımak; analizi tek-atış üretimden, analistle konuşarak ilerleyen, kodun gerçeğine
dayanan bir sürece dönüştürmek.

**Yöneten kısıt:** Çalışan hiçbir akış ve ekran bozulmadan, eski kod kaybedilmeden
ilerlenir. Yeni yapı **paralel** kurulur, bayrak arkasında ship edilir, pilotta
doğrulanır; ekip her şey hazır olduğunda **tek seferde** geçiş yapar. Analistlerin
günlük çalışması hiçbir aşamada aksamaz.

---

## 01 · Mevcut durum — sağlam temel, net teknik borç

Mimari: Flask (~94 endpoint) + tek-dosya SPA (`templates/index.html`) + `run.py`
subprocess orkestratör + `workflow.py` durum makinesi + `skills/` modülleri;
varsayılan CLI modu (`claude -p`), RAG (`base.py`), MCP (Chrome/Jira/Postgres).

**Üzerine inşa edeceğimiz güç**
- **Modüler skills** — süreç/teknik/BRD/kapsam/delta, jira, mutabakat, mockup,
  telemetri ayrı dosyalarda; yeni yeteneği izole eklemeye uygun.
- **Çalışan pipeline** — Süreç→Teknik→Jira ve BRD→Kapsam uçtan uca üretimde.
- **RAG + canlı gözlem** — referans okuma ve Chrome MCP ile canlı uygulama gözlemi var.
- **Telemetri** — kim ne kadar iş yapıyor ölçülüyor; v2 kararlarını veriyle vereceğiz.

**Aşacağımız teknik borç**
- **Monolitik arayüz** — tüm ekranlar tek dev `index.html`'de; büyük değişiklik
  kırılgan. v2'nin ilk hedefi.
- **Tek-atış analiz** — üretim etkileşimsiz; analist sürece müdahale edemiyor.
- **CLI stateless** — her çağrı bağımsız; sohbet/oturum bağlamı ek mimari ister.
- **Yarı-sabit akış** — yeni akış eklemek `run.py`/`workflow.py` değişikliği gerektiriyor.
- **Kod tabanına körlük** — analiz gerçek uygulama koduna dayanmıyor; etki analizi yok.

---

## 02 · Vizyon → teknik yaklaşım

| Hedef | Bugün | v2 yaklaşımı | Zorluk |
|---|---|---|---|
| Ekran tasarımı (süreç · BRD · teknik) | Tek dosyada, işlevsel ama uygulama hissi zayıf | Ekranları bileşenlere ayır; app-like, hızlı | Orta |
| Sohbetle düzeltme | `yeniden_calistir` + delta; tam sohbet yok | Analize bağlı durumlu chat oturumu; bölüm-hedefli düzenleme | Yüksek |
| Etkileşimli soru sorma | Açık sorular analiz SONRASI listeleniyor | Üretimden önce/sırasında netleştirici soru fazı | Orta |
| Kolay yeni akış | Akış eklemek kod değişikliği ister | Deklaratif akış tanımı (config-driven pipeline) | Orta |
| Kod reposu → etki analizi | Yok — analiz gerçek koda kör | MCP dosya/git + kod-RAG; etki analizi | Yüksek |
| Referansları doğru okuma | Keyword-tabanlı parçalama, boyut limiti | Semantik retrieval (embedding) | Orta |
| MCP'den daha iyi faydalanma | Chrome var; Jira/Postgres az kullanılıyor | MCP'leri analiz yoluna doğru bağla (`--allowedTools`) | Düşük-Orta |
| Gerçek uygulama hissi | Kullanım paneli iyi; geneli değişken | Tutarlı bileşen dili, durum/geri bildirim, performans | Orta |

---

## 03 · Strateji — paralel klon uygulama

**Karar:** v2, mevcut uygulamanın **ayrı bir klonu** olarak kurulur. Eski uygulamaya
tek satır dokunulmaz; analistler onu kullanmaya devam eder. Yeni uygulama izole
geliştirilip test edilir; kanıtlanınca eski kaldırılıp v2'ye geçilir.

1. **Paralel klon** — v2 ayrı dizin/port/instance. Eski uygulama hiç değişmez.
2. **Eski donduruldu** — analistler eskiyi kullanmaya devam; eskiye yalnız kritik bugfix.
3. **Ortak yapılandırma** — referanslar, Jira/Confluence, canlı-app ayarları paylaşılır/kopyalanır.
4. **v2'de test & düzeltme** — tüm testler ve hata gidermeler klonda; analistler etkilenmez.
5. **Cutover** — v2 kanıtlanınca eski kaldırılır, ekip tek seferde geçer. Geri dönüş: `v1-stable` etiketli sürüm hazır bekler.

---

## 04 · Fazlı yol haritası

Her faz bayrak arkasında kurulur, pilotta test edilir, kararlıyken merge edilir —
sonraki faza ancak öncekinin çalışan hâli yayınlandığında geçilir.

### Faz 0 — v2 klonunu kur (Temel · altyapı)
Mevcut uygulamayı ayrı çalışma alanına klonla; eskiyi dokunmadan izole geliştirme + test ortamı.
- Kodu ayrı dizin/instance'a klonla, ayrı portta çalıştır — eski `5002`'de kesintisiz sürer.
- Ortak yapılandırma (referanslar, Jira/Confluence, canlı-app) paylaşımı/kopyası.
- Eski kararlıyı etiketle (rollback çapası); v2 dalını aç.
- Arayüzü v2'de ekran-eklenebilir hâle modülerleştirmeye başla.
- **Çıktı:** İzole v2 çalışma alanı; eski üretimde kesintisiz.

### Faz 1 — Etkileşimli & sohbetli analiz (Çekirdek değer · hedef 2·3)
Analistin deneyimini tek-atıştan, konuşarak ilerleyen sürece çevirir — en yüksek değer.
- Netleştirici-soru fazı: üretimden önce eksik/muğlak noktaları sor.
- Sohbetle düzeltme: analize bağlı chat oturumu; "şu bölümü değiştir" → hedefli düzenleme.
- Değişiklik geçmişi & onay: her düzeltme izlenir, analist onaylar.
- **Çıktı:** Daha doğru, kaliteli analiz; analist kontrolde.

**Uygulama durumu (2026-09-09):**
- ✅ **Artım 1 — belkemiği:** `skills/revizyon.py` — analiz-bağlı revizyon oturumu
  (versiyon snapshot'ları, değişiklik geçmişi, onay/ret, geri-al, diff). Deterministik,
  0 token; 20 assert'lik test geçti. Mevcut analiz akışına dokunmuyor (ayrı `output/revizyon/`).
- ✅ **Artım 2 — bölüm-hedefli düzenleme:** `skills/revizyon_ai.py` — `bolumlere_ayir`
  (başlık-tabanlı, iç içe olmayan bölümleme), `bolum_bul` (ID/başlık ile), `bolum_duzenle`
  (yalnız hedef bölümü AI'a gönderir, splice eder, `revizyon_oner` ile beklemede öneri).
  Tam yeniden-üretim yok. Deterministik parçalar 11 assert ile test edildi; tek AI çağrısı
  izole + enjekte-edilebilir (`_ai_fn`), kota harcanmadı.
- ✅ **Artım 3 — endpoint'ler + UI (TAMAM):** `app.py` `/api/revizyon/*` (baslat, ozet,
  bolum-duzenle, onayla, reddet, geri-al, diff). CSRF + `IZIN_VERILEN_CIKTILAR` korumalı;
  `onayla`/`geri-al` gerçek çıktı dosyasını yazar. UI: ayrı **Revizyon** ekranı
  (`templates/screens/revizyon.html`, Faz 0 include mekanizması) — dosya seçici, bölüm-hedefli
  düzeltme formu, renkli diff'li bekleyen-öneri kartı (Onayla/Reddet), değişiklik geçmişi
  timeline'ı, versiyonlar + geri-al. Tarayıcıda uçtan uca doğrulandı (oturum → öneri → renkli
  diff → onayla → çıktıya yazım; konsol hatasız). `bolum-duzenle` AI kısmı kota nedeniyle
  canlı çalıştırılmadı (Artım 2'de enjekte AI ile test edilmişti). Bkz. `docs/ENDPOINTS.md`.

> **Faz 1 durumu:** Backend + endpoint + UI tamam ve doğrulandı. Sıradaki: netleştirici-soru
> fazının üretim-öncesi akışa bağlanması ve (Faz 2'de) revizyon panelinin çıktı görüntüleyiciyle
> bütünleştirilmesi. Canlı AI ile tek uçtan-uca prova, kota uygun olduğunda analistçe yapılmalı.

### Faz 2 — Ürün kalitesi: tasarım sistemi, iş akışı, yetki, otomasyon (Deneyim · hedef 1·8)
Aktif kullanılan ürünü, tasarım ekibinden çıkmış gibi tutarlı/kullanıcı-dostu/yönetilebilir hâle getir.
Kaynak öneri artifact: `18f4d542-52ca-4705-8633-960ca079dfca`.

**Onaylanan kararlar (2026-09-09):**
- **Roller:** yalnız **Owner + Analist**. Analist, owner'ın özellikle gizlediği ekran/buton hariç
  HER ekran ve işlemi kullanır → basit "owner + görünürlük yönetimi" modeli (rol matrisi değil).
  Yönetim ekranları (kullanıcılar, kullanım, görünürlük) owner-only.
- **Yöntem:** ÖNCE mockup (Süreç · Çıktılar · Menü), onay sonrası kod.
- **Otomatik güncelleme:** bildirimli otomatik (analiz yokken sessiz uygula; iş sürerken "yeni
  sürüm hazır" göster, iş bitince uygula).
- **Ek öneriler dahil:** analiz oturumu/proje kavramı, sağlık paneli, komut paleti, boş
  durumlar/onboarding, changelog, hata/bildirim standardı, erişilebilirlik, hafif regresyon güvencesi.

**Sıralı alt-fazlar:**
- ✅ 2.0 Tasarım sistemi — mockup onaylandı (artifact `fa43b8e2`, 3 ekran); `static/ds.css`
  ds-* bileşen katmanı (ek; eski ekranlar etkilenmez).
- ✅ 2.1 Çıktılar — `/api/oturum` (tazelik: çıktı mtime ≥ oturum başlangıcı → güncel) +
  `templates/screens/ciktilar.html` (oturum barı, kaynak/zaman/sürüm + rozet, arşiv, boş durum).
  Eski görüntüleyici "Görüntüleyici" olarak kaldı; "İncele" ona devreder. Tarayıcıda doğrulandı.
- ✅ 2.2 Süreç ekranı yeniden kurgu — ID/handler'lara dokunmadan cerrahi yeniden sıralama:
  Girdi → **Bağlam Filtresi** (etiket: HAZIRLIK · ÜRETİMDEN ÖNCE) → **Gelişmiş — Özel Prompt**
  (İSTEĞE BAĞLI, en altta). **Delta / CR** ayrı ekran (`screens/delta.html`, nav Pipeline altında;
  `da-*` ID'leri korundu → mevcut `deltaAnaliziBaslat()` aynen çalışır). Tarayıcıda doğrulandı.
  (Revizyon panelinin süreç ekranına gömülmesi 2.6'ya bırakıldı — Revizyon ekranı zaten var.)
- ✅ 2.3 Menü / bilgi mimarisi — sidebar iş akışına göre yeniden gruplandı (nav-item'lar
  verbatim): **Analiz** (Süreç · BRD · Delta) → **Çıktılar & Revizyon** (Çıktılar · Görüntüleyici ·
  Revizyon · Geçmiş) → **Jira** → **Kaynaklar** (Referanslar · Kılavuz) → **Yönetim** 🔒 (Ayarlar ·
  Jira Ayarları · Promptlar · Güncelleme · Kullanım). Rol-duyarlı gizleme 2.4'te.
- ✅ 2.4 Owner/Analist + görünürlük yönetimi + denetim logu — kullanıcı yönetimi zaten vardı
  (Ayarlar, `/api/users`). Eklenen: `_owner_mi/_rol`, `GIZLENEBILIR_KATALOG` (10 ekran/aksiyon),
  `gorunurluk.json` (repoda izlenir), `/api/gorunurluk` GET/POST, sunucu tarafı engel
  (`gorunurluk_kontrol`), `skills/denetim.py` + `/api/denetim` + 11 emit noktası, UI
  `_rolUygula()` + **Yetki & Denetim** ekranı (`screens/yetki.html`, Yönetim 🔒). Doğrulandı.
- ✅ 2.5 Otomatik güncelleme & yeniden başlatma — bildirimli otomatik: arka plan `git fetch`;
  iş yokken sessiz `pull --ff-only` + restart, iş sürerken "yeni sürüm hazır" banner'ı ve iş bitince
  uygulama; yerel değişiklik / push edilmemiş commit varsa yalnız bildirir (owner makinesi korunur).
  `/api/guncelleme/durum|simdi`, `screens/_guncelleme.html`, `AUTO_UPDATE`/`AUTO_UPDATE_INTERVAL`.
- ✅ 2.6 Ek özellikler — **Sistem Sağlığı** (`/api/saglik` + `screens/saglik.html`: sürüm, CLI kota,
  güncelleme, workflow, MCP, disk, auth), **komut paleti** ⌘K (`screens/_palet.html`, rol-duyarlı),
  **regresyon güvencesi** (`tests/smoke_test.py` 24 kontrol + `tests/test_revizyon.py` 15 assert),
  rehberli boş durumlar (ds-empty; Çıktılar/Yetki/Sağlık), changelog banner'da (2.5), odak/azaltılmış
  hareket (ds.css). Tarayıcıda doğrulandı.
- **Çıktı:** Verimli, ürün gibi hissettiren, yönetilebilir, kendini güncelleyen uygulama.

> **Faz 2 durumu (2026-09-09): 2.0–2.6 TAMAM.** Tüm ekranlar 5003'te doğrulandı, 5002 dokunulmadı.
> Kalan bilinçli açık uçlar: (1) eski ekranların (Süreç/BRD/Jira/Ayarlar) gövdesi hâlâ `index.html`
> içinde — partial'lara taşıma kademeli; (2) revizyon panelinin Süreç ekranına gömülmesi; (3) canlı AI
> ile `bolum-duzenle` provası — **✅ CANLI DOĞRULANDI (2026-09-09):** claude CLI ile PA-001'e 2FA
> düzenlemesi; yalnız hedef satır değişti, komşular (PA-002/Amaç/Açık Sorular) ve başlık korundu,
> onayla → çıktıya yazıldı. Tam yeniden-üretim yok; (4) ✅ AUTH açık Owner/Analist enforcement
> `tests/test_auth_roller.py` ile doğrulandı (23 kontrol; gerçek .env/users.json'a dokunmaz).
>
> **Kalan (isteğe bağlı, düşük öncelik):** eski ekran gövdelerinin (Süreç/BRD/Jira/Ayarlar) partial'lara
> taşınması; revizyon panelinin Süreç ekranına gömülmesi. İkisi de Faz 3'e engel değil.

### Faz 3 — Gerçeğe dayanan analiz: kod, referans, MCP (Derinlik · hedef 5·6·7)
Analizi gerçek uygulamanın çalışma prensibine bağla. Kod reposu bağlantısı **şimdi
yapılmaz** — altyapı buna hazır kurulur.
- Kod-kaynağı soyutlaması (MCP dosya/git arayüzü) hazır kurulur; gerçek repo bağlantısı sonraya.
- Etki analizi iskeleti — bir değişiklik hangi kod yollarını/tabloları/servisleri etkiler.
- Semantik referans retrieval + Postgres/Jira MCP'lerini analiz yoluna bağla (şimdi devrede).
- **Çıktı:** Repoya hazır altyapı; bağlanınca gerçeğe dayanan analiz & etki analizi.

**Uygulama durumu (2026-09-09):**
- ✅ **3.a Kod-kaynağı soyutlaması:** `skills/kod_kaynagi.py` — salt-okuma, yol-güvenli (repo köküne
  hapsedilmiş), deterministik (0 token) yerel git/dosya arayüzü: repo durumu (git/branch/dil), dosya ağacı,
  dosya okuma, arama (ripgrep/python), git geçmiş. Config makineye özel (`reference/kod_kaynagi.json`,
  gitignore + `.example` seed). `/api/kod/*` (config owner-only) + `screens/kod.html` (Kaynaklar).
  17 assert test (yol kaçışı reddi dahil). **Gerçek repo bağlantısı analiste bırakıldı** (yol haritası kararı).
- ⏳ 3.b Etki analizi iskeleti — analiz çıktısındaki varlıkları (tablo/ekran/endpoint) kod aramasına bağla.
- ⏳ 3.c Semantik referans retrieval + Postgres/Jira MCP entegrasyonu.

### Faz 4 — Genişletilebilirlik & yayın (Ölçek · hedef 4)
Yeni akışları kod yazmadan ekleyebilir hâle getir; v2'yi tüm ekibe aç.
- Deklaratif akış tanımı — yeni istek/akış = konfigürasyon, kod değil.
- Pilot analist → tüm ekip rollout; eski akışlar geri-uyumlu kalır.
- Dokümantasyon & KILAVUZ güncelleme; eğitim.
- **Çıktı:** Kendini büyütebilen, ekibe yayılmış v2.

---

## 05 · Riskler & azaltım

- **Monolit kırılganlığı** — Tek-dosya arayüzde büyük değişiklik ekranları bozabilir.
  *Azaltım:* Faz 0 modülerleştirme; v2 ekranları ayrı, eskiye dokunmadan; bayrak + pilot.
- **CLI kota baskısı** — Etkileşim/sohbet AI çağrılarını çoğaltır; 5-saatlik limit zorlanabilir.
  *Azaltım:* Verimli prompt + önbellek; ağır etkileşimde API modu; kota-farkında tasarım.
- **Kod-repo ölçek & güvenlik** — Büyük repoları indekslemek maliyetli; erişim güvenlik ister.
  *Azaltım:* Tam ingest yerine talep-anında retrieval (MCP); salt-okuma; kapsam sınırı.
- **Durumlu sohbet + stateless CLI** — Oturum bağlamını taşımak ek mimari.
  *Azaltım:* Konuşma geçmişini açık taşı; küçük, hedefli düzenleme çağrıları.
- **Kapsam kayması** — Sekiz hedef aynı anda ilerlerse hiçbiri bitmez.
  *Azaltım:* Faz sırası katı; her faz yayınlanmadan sonrakine geçilmez.

---

## 06 · Çalışma modeli

Bu plan kalıcı çapa; uygulama faz-başına yeni, odaklı context'lerde yürür. Her context
tek faza odaklı, bu plana referanslı.

**Netleşen kararlar:**
- **Kod reposu** — şimdi bağlanmaz; altyapı buna hazır kurulur (Faz 3).
- **AI modu** — şimdi Claude CLI; ileride her analiste Claude Team üyeliği → her analist
  kendi kotasıyla (telemetri zaten per-analist atıf yapıyor, mimari buna hazır).
- **Yayın** — pilot = tüm analistler, ama paralel klon ile: eski uygulama kesintisiz sürer,
  v2'de test & hata giderme yapılır, hazır olunca cutover.

---

## Faz 0 uygulama durumu (bu klon)

| Öğe | Değer |
|---|---|
| Klon dizini | `/Users/dt/brd-analyst-agent-v2` |
| Git dalı | `v2` (remote: `Analysys_Agent`) |
| Rollback çapası | `v1-stable` etiketi (commit `40c847c`) |
| v2 portu | **5003** (`PORT=5003 ./start.sh`) |
| Eski (dokunulmaz) | `5002` — `/Users/dt/brd-analyst-agent`, kesintisiz |
| Ortak config | `.env`, `reference/{context_filter,prompts,sources}.json`, `users.json` elle kopyalandı (gitignore) |

**İki instance aynı anda:** 5002 (eski, üretim) ve 5003 (v2 klon) bağımsız çalışır.
