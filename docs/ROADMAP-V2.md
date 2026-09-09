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

### Faz 2 — Süreç · BRD · Teknik ekran tasarımı (Deneyim · hedef 1·8)
Üç çekirdek ekranı, Faz 1'in etkileşimli akışıyla entegre, gerçek uygulama kalitesinde.
- App-like düzen: net durum, hızlı geri bildirim, performanslı büyük-çıktı gösterimi.
- Sohbet + soru akışını ekranın doğal parçası yap (yan panel / thread).
- Tutarlı bileşen dili (Kullanım paneli kalitesi tüm ekranlara).
- **Çıktı:** Verimli, ürün gibi hissettiren analiz ekranları.

### Faz 3 — Gerçeğe dayanan analiz: kod, referans, MCP (Derinlik · hedef 5·6·7)
Analizi gerçek uygulamanın çalışma prensibine bağla. Kod reposu bağlantısı **şimdi
yapılmaz** — altyapı buna hazır kurulur.
- Kod-kaynağı soyutlaması (MCP dosya/git arayüzü) hazır kurulur; gerçek repo bağlantısı sonraya.
- Etki analizi iskeleti — bir değişiklik hangi kod yollarını/tabloları/servisleri etkiler.
- Semantik referans retrieval + Postgres/Jira MCP'lerini analiz yoluna bağla (şimdi devrede).
- **Çıktı:** Repoya hazır altyapı; bağlanınca gerçeğe dayanan analiz & etki analizi.

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
