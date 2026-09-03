# Kullanım Telemetrisi — Google Apps Script (write-only) Kurulumu

Amaç: Her analistin lokal Analyst Studio'su kullanım olaylarını **yalnız yazabildiği** merkezî
bir Google Sheet'e gönderir. Sheet **sadece sende** (owner). Analistler hiçbir şey okuyamaz.
Yalnız metadata gider — BRD/analiz içeriği ASLA.

## 1. Google Sheet oluştur
1. https://sheets.google.com → yeni boş sheet (ör. adı **"Analyst Studio Kullanım"**).
2. Bu sheet senin Google hesabında; kimseyle paylaşma.

## 2. Apps Script'i ekle
1. Sheet'te **Uzantılar → Apps Script**.
2. Açılan editöre aşağıdaki kodu yapıştır (mevcut içeriği sil):

```javascript
// Yazma (analist app'leri) + owner okuma anahtarı.
const OKUMA_ANAHTARI = 'BURAYA-UZUN-RASTGELE-ANAHTAR';   // owner .env → USAGE_SINK_KEY
const YAZMA_TOKEN   = '';                                 // opsiyonel: doluysa POST'ta ?t=<token> beklenir

function _sheet() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
}

function _basliklar(sh) {
  if (sh.getLastRow() === 0) {
    sh.appendRow(['ts','analist','olay','durum','sure_ms','model','ai_modu',
                  'jira_toplam','proje','dokuman','makine','app_versiyon']);
  }
}

function doPost(e) {
  try {
    if (YAZMA_TOKEN && (!e.parameter || e.parameter.t !== YAZMA_TOKEN)) {
      return ContentService.createTextOutput('forbidden');
    }
    const o = JSON.parse(e.postData.contents || '{}');
    const sh = _sheet(); _basliklar(sh);
    const jira = o.jira && typeof o.jira === 'object' ? (o.jira.toplam || 0) : '';
    const baglam = o.baglam || {};
    sh.appendRow([o.ts||'', o.analist||'', o.olay||'', o.durum||'', o.sure_ms||'',
                  o.model||'', o.ai_modu||'', jira,
                  baglam.proje||'', baglam.dokuman||'', o.makine||'', o.app_versiyon||'']);
    return ContentService.createTextOutput('ok');
  } catch (err) {
    return ContentService.createTextOutput('error');
  }
}

function doGet(e) {
  // Owner okuma: ?read=<OKUMA_ANAHTARI> → tüm olayları JSON dizi döndürür.
  if (!e.parameter || e.parameter.read !== OKUMA_ANAHTARI) {
    return ContentService.createTextOutput('forbidden');
  }
  const sh = _sheet();
  const veri = sh.getDataRange().getValues();
  const bas = veri.shift() || [];
  const olaylar = veri.map(function(r) {
    const o = {}; bas.forEach(function(k, i) { o[k] = r[i]; });
    return {ts:o.ts, analist:o.analist, olay:o.olay, durum:o.durum,
            sure_ms:o.sure_ms, model:o.model, ai_modu:o.ai_modu,
            jira:{toplam:o.jira_toplam||0},
            baglam:{proje:o.proje, dokuman:o.dokuman},
            makine:o.makine, app_versiyon:o.app_versiyon};
  });
  return ContentService.createTextOutput(JSON.stringify(olaylar))
         .setMimeType(ContentService.MimeType.JSON);
}
```

3. `OKUMA_ANAHTARI` değerini uzun rastgele bir metinle değiştir (ör. bir parola üreticiden).

## 3. Web App olarak yayınla
1. Sağ üst **Dağıt → Yeni dağıtım**.
2. Tür: **Web uygulaması**.
3. "Şu kişi olarak çalıştır": **ben (senin hesabın)**.
4. "Erişimi olan": **Herkes** (analistlerin POST edebilmesi için — okuma yine anahtarla korunur).
5. **Dağıt** → çıkan **Web App URL**'ini kopyala.

## 4. Analist makinelerine (herkese)
Her analistin `.env`'ine ekle:
```
USAGE_SINK_URL=<Web App URL>
ANALYST_NAME=<analistin adı>     # AUTH kapalıysa atıf için
```
> `USAGE_DASHBOARD` ve `USAGE_SINK_KEY` analist makinelerine **EKLENMEZ** — onlar yalnız yazar, görmez.

## 5. Owner makinesine (yalnız sen)
`.env`'ine ekle:
```
USAGE_DASHBOARD=true
USAGE_SINK_URL=<Web App URL>
USAGE_SINK_KEY=<OKUMA_ANAHTARI ile aynı değer>
```
Uygulamayı yeniden başlat → sol menüde **"Kullanım"** sekmesi çıkar. **Uzaktan Çek** ile ekip verisini Sheet'ten çeker; tablo + Excel export hazır.

## Notlar
- Yalnız metadata gönderilir (analist, olay tipi, süre, durum, model, açılan task adedi, proje/doküman adı). İçerik yok.
- Transport başarısız olursa (ağ yok) olay lokal `logs/usage/events.jsonl`'de kalır; kaybolmaz.
- İlerde paylaşmak istersen: Sheet'i salt-okunur paylaş veya owner listesini genişlet.
