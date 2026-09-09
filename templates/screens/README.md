# templates/screens — Ekran-eklenebilir mimari (v2 · Faz 0)

Monolitik `templates/index.html` (~7500 satır, tek dosya SPA) v2'de **ekran-eklenebilir**
hâle getiriliyor. Amaç: yeni bir ekran eklemek/değiştirmek için dev dosyayı elle
kesmek yerine, her ekranın markup'ı kendi partial dosyasında yaşasın.

## Mekanizma

Flask `render_template("index.html")` + Jinja `{% include %}` kullanır
(`TEMPLATES_AUTO_RELOAD=True` — dosya değişince otomatik tazelenir). Her ekran bloğu:

```
templates/screens/<ekran>.html   →  <div class="page" id="page-<ekran>"> … </div>
```

`index.html` içinde ilgili yerde yalnız:

```jinja
{% include "screens/<ekran>.html" %}
```

Render çıktısı, blok satır-içi dururkenki ile **işlevsel olarak aynıdır** (Jinja içeriği
olduğu gibi yerleştirir). Böylece:
- Yeni ekran = yeni partial dosyası + bir `{% include %}` satırı + `switchTab` init kancası.
- Ekran değişikliği tek, küçük dosyada; büyük `index.html` diff'i yok.

## Mevcut durum

- **`kilavuz.html`** — Faz 0'da `index.html`'den ÇIKARILAN ilk ekran (mekanizma kanıtı).
- **`revizyon.html`** — Faz 1'de bu mekanizmayla EKLENEN yeni ekran (sohbetle bölüm-hedefli
  düzeltme + değişiklik geçmişi + onay/ret). Kendi `<style>` + `<script>`'ini taşır; nav item,
  `switchTab` kancası (`rzYukle`) ve crumb etiketi `index.html`'de. **Dikkat:** partial Jinja ile
  render edildiğinden CSS/JS'te `{#`, `{{`, `{%` dizilerinden kaçın (ör. `@media(...){ #id` —
  `{` ile `#` arasına boşluk).
- **`ciktilar.html`** — Faz 2.1: aktif oturum + tazelik/köken/sürüm + arşiv (`/api/oturum`, `ds-*`).
- **`delta.html`** — Faz 2.2: Delta/CR analizi Süreç ekranından ayrı ekrana taşındı (`da-*` ID'leri
  korundu; JS index.html'de). Statik — `switchTab` kancası gerekmez.
- Bileşen dili: `static/ds.css` (`ds-*`). Yeni ekranlar bu vokabülerden kurulur.
- Kalan eski ekranlar hâlâ `index.html` içinde satır-içi; kademeli taşınacak.

## Yeni ekran ekleme adımları (hedeflenen akış)

1. `templates/screens/<ekran>.html` oluştur: `<div class="page" id="page-<ekran>"> … </div>`.
2. `index.html`'de `.main` içine `{% include "screens/<ekran>.html" %}` ekle.
3. Sidebar'a `nav-item` + `switchTab('<ekran>')` ekle.
4. Gerekliyse `switchTab` içine ekranın init kancasını ekle (ör. veri yükleme).

> Not: `switchTab` router'ı ve sidebar hâlâ elle güncellenir. Tam data-driven
> **ekran registry** (nav + routing tek tanımdan) Faz 2 kapsamındadır; bkz.
> `docs/ROADMAP-V2.md` Faz 2.
