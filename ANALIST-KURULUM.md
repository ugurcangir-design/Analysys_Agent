# Analyst Studio (v2) — Analist Kurulum Kılavuzu

Bu kılavuz, **test sürümü v2**'yi kendi Mac'inize kurmanız içindir. Adımları **sırayla** izleyin.
Takıldığınız yerde en alttaki "Sorun Giderme" bölümüne bakın veya ekip liderine yazın.

> Not: v2, mevcut sürümle (5002) çakışmaz; ikisi aynı anda çalışabilir. v2 **5003** portunda açılır.

---

## Bölüm A — Şirket Claude hesabı ve araçlar (bir kez)

### A1. Homebrew (yoksa)
Terminal'i açın (Spotlight → "Terminal") ve kurulu mu bakın:
```bash
brew --version
```
Sürüm görünmüyorsa Homebrew'i kurun:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### A2. Python 3.10+ ve Node.js
```bash
python3 --version    # 3.10 veya üzeri olmalı
```
Eski/yoksa:
```bash
brew install python@3.12
```
Node.js (Claude CLI için gerekli):
```bash
node --version || brew install node
```

### A3. Claude Code CLI kurulumu
```bash
npm install -g @anthropic-ai/claude-code
```

### A4. ŞİRKET Claude hesabıyla giriş (ÖNEMLİ)
Terminalde şu komutu çalıştırın:
```bash
claude
```
Açılan akışta **"Log in with Claude account"** seçin → tarayıcı açılır → **şirket e-postanızla**
(…@sans-technology.com) giriş yapın ve yetkilendirin. Giriş bitince terminale dönebilirsiniz.

- Giriş **makine geneli** tektir: bir kez şirket hesabıyla girdikten sonra tüm analizler bu hesaptan
  (Demiroren Teknoloji aboneliği) çalışır ve kullanım şirkete sayılır.
- "Erişiminiz yok / abonelik bulunamadı" gibi bir uyarı alırsanız hesabınız henüz Claude Code'a
  yetkilendirilmemiştir → ekip liderine bildirin.

### A5. Girişi doğrulayın
```bash
claude
```
açıldıktan sonra içine `/status` yazın; **e-posta adresinizin @sans-technology.com** ve organizasyonun
**Demiroren Teknoloji** olduğunu görün. Çıkmak için `/exit`.

---

## Bölüm B — Uygulamayı kurma (bir kez)

### B1. Depoyu indirin (v2 dalı)
Projeyi koymak istediğiniz klasöre geçip (örn. ana klasör), v2 dalını klonlayın:
```bash
cd ~
git clone -b v2 https://github.com/ugurcangir-design/Analysys_Agent.git analyst-studio-v2
cd analyst-studio-v2
```
> GitHub deposuna erişiminiz yoksa (özel depo) ekip liderinden davet/erişim isteyin.

### B2. Kurulumu çalıştırın
```bash
bash setup.sh
```
Bu komut: sanal ortamı kurar, paketleri yükler, `.env` dosyasını **doğru varsayılanlarla** oluşturur
(CLI modu açık, port 5003) ve masaüstünde **"Analyst Studio v2"** ikonu oluşturur.

> `.env` dosyasına dokunmanıza gerek yok — analist için hazır gelir.
> Kurulumda "swiftc bulunamadı / ikon oluşmadı" derse sorun değil; `./start.sh` ile açarsınız.

---

## Bölüm C — Başlatma ve ilk ayar

### C1. Uygulamayı başlatın
Masaüstündeki **Analyst Studio v2** ikonuna çift tıklayın, **veya** terminalden:
```bash
./start.sh
```
Tarayıcıda açın: **http://localhost:5003**

### C2. Adınızı tanımlayın (bir kez)
**Ayarlar → "Analist Adı Soyadı"** alanını doldurun. (Kullanım raporlarında kimlik içindir; makineye özeldir.)

### C3. Hazır olduğunu doğrulayın
**Ana Sayfa**'da:
- "AI / Kota" kartında **CLI hazır** yazmalı (analiz modeli varsayılan **Sonnet 5** — dilerseniz buradan değiştirebilirsiniz).
- Bir süreç/BRD dokümanı yükleyip küçük bir analiz başlatarak akışın çalıştığını görün.

---

## Bölüm D — Test sırasında bilmeniz gerekenler

- **Doküman formatı:** CLI modu **görsel/taranmış** BRD analiz edemez. Doküman **metin tabanlı** olmalı:
  PDF (metinli) · DOCX · TXT · MD. Taranmış belge için önce OCR uygulayın.
- **Görünüm:** Süreç ve BRD ekranları **tek kolon adım akışı** (ray) ile gelir — yalnız sıradaki adım açıktır,
  bitenler tek satıra iner. Eski düzeni isterseniz ekran sağ üstündeki **"Klasik görünüm"** ile anında dönersiniz.
- **Adım adım çalışma:** Onay ekranlarında **"Bu adımı düzelt"** kutusuna bir bölüm ID'si (örn. `PA-003`) veya
  bölüm adı yazıp yalnız o bölümü düzelttirebilirsiniz; teknik onayında **"◂ Süreç analizine dön"** ile önceki
  adıma dönmek süreci baştan çalıştırmaz.
- **Güncellemeler:** Uygulama boşta iken güncellemeleri **kendisi çeker ve yeniden başlar** — sizin `git pull`
  yapmanıza gerek yok. (Yerelde dosyaları elle değiştirmediğiniz sürece.)
- **Durdurma:** Çalışan bir analizi "Durdur" ile gerçekten durdurabilirsiniz; ekran değiştirmeniz analizi kesmez.

---

## Bölüm E — Sorun Giderme

| Belirti | Çözüm |
|---|---|
| `claude` "kullanım limiti / oturum düştü" diyor | Terminalde `claude` → `/login` ile şirket hesabına tekrar girin, uygulamayı yeniden başlatın. |
| Ana Sayfa'da "CLI limitte/bilinmiyor" | Bir terminalde `claude` → `/status` ile hesabı ve kotayı kontrol edin. |
| "swiftc bulunamadı" (kurulumda) | İkon atlanır, sorun değil. `./start.sh` ile başlatın. |
| "Python 3.10 gerekli" | `brew install python@3.12` → tekrar `bash setup.sh`. |
| Sayfa açılmıyor (5003) | Uygulamanın çalıştığından emin olun (ikon/`./start.sh`); tarayıcıda `http://localhost:5003`. |
| Analiz hata verdi | Ekrandaki hata kartı "ne oldu / ne yapmalı" der; teknik ayrıntıyı "Teknik ayrıntı" altından açıp ekip liderine iletin. |

---

**Yeniden başlatma:** kod güncellemesinden sonra uygulama kendini yeniden başlatır. Elle gerekirse
uygulama içinde **Güncelleme → "Yeniden Başlat"** kullanın.

Sorularınız için: ekip lideri (uygulama sahibi).
