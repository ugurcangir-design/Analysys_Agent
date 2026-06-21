# Güvenlik, Dağıtım ve Onboarding

> Ana referans: [CLAUDE.md](../CLAUDE.md). Güvenlik/auth/dağıtım kod yolu
> değiştiğinde burayı güncelle.

## Dağıtım Modeli

**Birincil model:** Lokal kurulum — her analist kendi makinesinde Analyst Studio
çalıştırır. Doğal paralellik + tam izolasyon. KILAVUZ Bölüm 14.1.

**Sunucu modu (HOST=0.0.0.0 + AUTH):** ⚠ Deneysel, üretimde test edilmedi,
şu an önerilmez. KILAVUZ Bölüm 14.4'te "deprecated" işaretli. Kod halen yerinde
(silinmedi) ama yeni geliştirme bu yola odaklanmamalı. Bakım yükü:
auth/admin/brute-force/CSRF kod yolları her güvenlik commit'inde test edilmeli.

## Güvenlik Mimarisi

### Auth (opsiyonel — AUTH_ENABLED env ile aç/kapa, sunucu modu için)
- Varsayılan **kapalı** (kişisel masaüstü kullanımı için — birincil)
- Açıkken `session["username"]` üzerinden cookie-based auth
- Şifre hash: `werkzeug.security.generate_password_hash` (scrypt)
- `users.json` dosyasında saklanır; `manage_users.py` CLI ile eklenir
- Brute-force koruması: IP başına 5 deneme/60s (RAM'de)
- `_admin_mi()`: env `ADMIN_USER` ile eşleşen username admindir

### CSRF — Origin/Referer kontrolü
- `csrf_kontrol()` before_request: POST/PUT/PATCH/DELETE'te kaynak host_url ile eşleşmeli
- Eşleşmezse 403 + WARN log
- `CSRF_MUAF`: `/api/auth/login`, `/api/heartbeat`
- Belt-and-suspenders: `SESSION_COOKIE_SAMESITE=Lax` zaten cross-site POST'a cookie göndermez

### Admin Yetkisi (@admin_gerekli decorator)
Sadece yapılandırma/yönetim endpoint'lerinde:
- `POST /api/prompts/<id>` (AI davranışı)
- `POST /api/prompts/<id>/reset`
- `POST /api/git/pull` (uygulama güncelleme)
- `POST /api/reset` (workflow zorla sıfırla)
- AUTH kapalıyken decorator otomatik geçer (kişisel mod = herkes admin)

### Başlangıç Güvenlik Kontrolü
`_baslangic_guvenlik_kontrol()`:
- **Default `HOST=127.0.0.1`** (yalnız yerel)
- LAN'a açmak için `.env`'de `HOST=0.0.0.0`
- LAN açık + AUTH kapalı → uygulama BAŞLATILMAZ (3 çözüm önerisi gösterir)
- Override: `ALLOW_LAN_NO_AUTH=true` (bilinçli risk kabulü)

### Diğer
- `SESSION_COOKIE_HTTPONLY=True`, `SAMESITE=Lax`
- `SESSION_COOKIE_SECURE` env ile açılır (HTTPS deploy için)
- CSP, X-Frame-Options (**SAMEORIGIN** — Kılavuz iframe için), X-Content-Type-Options (`guvenlik_basliklari`)
- iframe sandbox: `allow-scripts allow-forms` (NO `allow-same-origin` → AI mockup parent DOM'a erişemez)
- `/kilavuz` route KILAVUZ.html'i serve eder → SPA'da "Kılavuz" sekmesinde iframe ile gösterilir
- `.env` chmod 0600, atomik yazım (tmp.replace)
- Path traversal: `_guvenli_yol()` helper'ı tüm dosya yolu girdilerinde kullanılır

## Onboarding (Yeni Başlayan Eğitimi)

İlk kez kullanan analistlere yardımcı olmak için iki katman:

### 1. Inline `.ipucu` tooltip'leri
Küçük `?` ikonu (`class="ipucu"` + `data-ipucu="..."`). Hover/odakta açıklama.
Şu an 4 yerde: Bağlam Filtresi, Sorular sekmesi, Kalite skoru, Cevapları Uygula.

### 2. `.onboard-banner` — sekme başına ilk gösterimde 1 kez
`localStorage.setItem('onboard.<anahtar>', 'done')` ile kapatılır.
`_ONBOARD_BANNER` map'inde tanımlı 5 sekme: surec, brd, output, referanslar, prompts.
Yeni banner: tabloya bir giriş ekle.
Sıfırlama: console'da `_onboardSifirla()`.
