# Analyst Studio v2 — Analist Kurulum & Erişim

> **Test sürümü.** v2, eski uygulamanın (port 5002) yanında **paralel** çalışır (port **5003**).
> Eski uygulamanız çalışmaya devam eder; v2'yi ayrı bir pencerede test edersiniz.

## Gereksinimler
- macOS · Python 3.10+ · `git`
- **Claude Code CLI** kurulu ve giriş yapılmış (analiz AI'ı bununla çalışır):
  ```bash
  npm install -g @anthropic-ai/claude-code   # kurulu değilse
  claude                                       # açılınca /login ile Claude.ai hesabınızla girin
  ```

## Kurulum (tek sefer)

1. **v2'yi ayrı bir klasöre klonla** (eski `brd-analyst-agent` klasörünüzün YANINA):
   ```bash
   cd ~   # ya da eski uygulamanın bulunduğu üst klasör
   git clone -b v2 https://github.com/ugurcangir-design/Analysys_Agent.git brd-analyst-agent-v2
   cd brd-analyst-agent-v2
   ```

2. **Ayarlarınızı taşı** (Jira/AI ayarları — eski uygulamanızdan):
   ```bash
   cp ../brd-analyst-agent/.env .env            # eski .env'inizi kopyalayın
   grep -q '^PORT=' .env || echo 'PORT=5003' >> .env   # v2 portu (eski app'le çakışmasın)
   # (İsteğe bağlı) senkronlanmış referanslarınızı da taşıyın:
   cp -r ../brd-analyst-agent/reference/{confluence,jira,services} reference/ 2>/dev/null || true
   cp ../brd-analyst-agent/reference/{context_filter,prompts,sources}.json reference/ 2>/dev/null || true
   ```
   > Eski uygulamanız yoksa: `cp .env.example .env` yapıp Jira/AI ayarlarını doldurun; referansları uygulama içinden **Referanslar → Senkronize** ile çekin.

3. **Kur** (venv + bağımlılıklar + masaüstü ikonu):
   ```bash
   bash setup.sh
   ```
   Bu, masaüstünüze **"Analyst Studio v2"** ikonu koyar (eski "Analyst Studio" ikonundan ayrı).

## Başlatma & Erişim
- **Masaüstü:** "Analyst Studio v2" ikonuna çift tıklayın → tarayıcıda `http://localhost:5003` açılır.
- **Terminal:** `./start.sh` → `http://localhost:5003`

## Güncelleme — otomatik
v2 kendini **otomatik günceller**: iş yapmadığınız bir anda yeni sürümü çeker ve sessizce yeniden başlar
(bir analiz sürerken kesmez). Üstte "Yeni sürüm hazır" bildirimi çıkarsa "Şimdi güncelle" ile hemen de
alabilirsiniz. Elle bir şey yapmanız gerekmez.

## Sık karşılaşılanlar
- **"Adres kullanımda" / boş sayfa:** Eski app da 5003'te olabilir. `.env`'de `PORT=5003` olduğundan ve
  eski uygulamanın 5002'de kaldığından emin olun.
- **Analiz "oturum süresi doldu" diyor:** Terminalde `claude` → `/login` ile yeniden giriş yapıp
  uygulamayı **Güncelleme → Yeniden Başlat** ile yeniden başlatın.
- **Masaüstü ikonu oluşmadı:** `xcode-select --install` sonra `bash create_app.sh`. İkon olmadan da
  `./start.sh` ile çalışır.

## Geri bildirim
Test sırasında takıldığınız/eksik bulduğunuz her şeyi not alın; v2 sizin geri bildiriminizle olgunlaşacak.
Eski uygulamanız hiçbir aşamada bozulmaz — güvenle deneyin.
