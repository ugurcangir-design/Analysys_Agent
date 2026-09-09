"""
Analist-dostu hata mesajları (v2 Faz 4) — 0 token, deterministik, BAĞIMSIZ (base.py import etmez;
workflow.py/run.py de kullanır).

Ham hata (`"Süreç analizi hatası: RuntimeError(...)\nTraceback ..."`) → {kategori, baslik, aciklama, oneri, ham}.
Analist teknik iz yerine "ne oldu / ne yapmalı" görür; ham metin UI'da katlanabilir ayrıntı olarak durur
(log'a zaten tam yazılır). Eşleşme yoksa `bilinmeyen` — ham metnin ilk satırı başlık olur.
"""
from __future__ import annotations

import re

# (kategori, regex [casefold], başlık, açıklama, öneri) — SIRA ÖNEMLİ: ilk eşleşen kazanır.
_KURALLAR: list[tuple[str, str, str, str, str]] = [
    ("durduruldu", r"durdur|sigterm|killed|signal 15",
     "İşlem durduruldu",
     "Analiz analist tarafından durduruldu ya da süreç dışarıdan sonlandırıldı.",
     "Gerekirse 'Yeniden Başlat' ile aynı dokümanla tekrar başlatın."),
    ("cli_limit", r"kullanım limitine|api_error_status.{0,6}429|rate.?limit|session limit|usage limit|too many requests|\b429\b",
     "Claude kullanım limiti doldu",
     "Claude aboneliğinin kullanım penceresi (5 saatlik oturum, haftalık kota veya usage-credit) tükendi; analiz çağrısı reddedildi.",
     "Belirtilen sıfırlama saatini bekleyin ya da terminalde `claude` → `/status` ile Claude Code'un kendi kota görünümüne bakın. Hemen devam gerekiyorsa .env'de ANTHROPIC_API_KEY ile API moduna geçin."),
    ("cli_oturum", r"oturumunun süresi doldu|oauth token expired|\b401\b|unauthorized|/login|not logged in|authentication.?error",
     "Claude oturumu düştü — yeniden giriş gerekiyor",
     "Claude CLI'ın Claude.ai oturumu sona erdi; analiz çağrıları yetkisiz sayıldı.",
     "Bir terminalde `claude` çalıştırıp `/login` ile yeniden giriş yapın, sonra uygulamayı yeniden başlatıp analizi tekrar deneyin."),
    ("api_key", r"invalid x-api-key|api key|api_key|permission_error|\b403\b|forbidden",
     "API anahtarı geçersiz veya yetkisiz",
     "Anthropic API anahtarı kabul edilmedi ya da bu işlem için yetkisi yok.",
     "Ayarlar'da anahtarı kontrol edin (.env `ANTHROPIC_API_KEY`) veya CLI moduna geçin (`USE_CLAUDE_CLI=true`)."),
    ("zaman_asimi", r"zaman aşımı|timeout|timed out|timeoutexpired|deadline",
     "İşlem zaman aşımına uğradı",
     "Analiz beklenen sürede tamamlanmadı — çok büyük doküman/referans seti, yavaş model yanıtı ya da canlı-uygulama gözleminin takılması olabilir.",
     "Bağlam Filtresi ile referansları daraltın, gözlem kapsamını küçültün veya daha hızlı bir model seçin; sonra 'Yeniden Başlat'."),
    ("disk", r"no space left|enospc|disk dolu|errno 28",
     "Disk dolu",
     "Çıktı yazılamadı — uygulamanın bulunduğu birimde yer kalmadı.",
     "Ana Sayfa → Disk temizlik → 'Şimdi temizle' ile eskimiş önbellek/log/arşivi silin ya da diskte yer açın."),
    ("ag", r"connection ?(error|refused|reset|aborted)|econnrefused|getaddrinfo|name or service not known|network is unreachable|ssl.?(error|certificate)|certificate_verify_failed|max retries exceeded|remote end closed",
     "Ağ bağlantısı kurulamadı",
     "Claude servisine, Atlassian'a ya da canlı uygulamaya ulaşılamadı (ağ kesintisi, VPN, proxy veya sertifika sorunu).",
     "İnternet/VPN bağlantısını ve varsa proxy ayarını kontrol edip 'Yeniden Başlat'."),
    ("mcp", r"playwright|chrome|mcp|allowedtools|browser|canlı uygulama.{0,40}(başarısız|hata|yapılamadı)",
     "Canlı uygulama gözlemi yapılamadı",
     "Chrome/Playwright MCP başlatılamadı ya da tarayıcı araçları reddedildi; analiz canlı gözlem olmadan devam edemedi.",
     "Ayarlar → Canlı Uygulama'da bağlantıyı test edin; sorun sürerse gözlemi kapatıp yalnız dokümanlarla analiz yapın."),
    ("model", r"model.{0,30}(not.?found|bulunamadı|not supported|invalid)|not_found_error",
     "Seçili model kullanılamıyor",
     "Analiz için seçilen model bu hesapta/planda yok ya da adı geçersiz.",
     "Ana Sayfa → AI / Kota kartından farklı bir model seçip tekrar deneyin."),
    ("dosya", r"filenotfound|no such file|çıktı yok|dosya bulunamadı|bulunamadı:|is a directory|permission denied|errno 13",
     "Dosya bulunamadı veya erişilemedi",
     "Beklenen girdi/çıktı dosyası yok ya da okunamıyor (silinmiş, taşınmış veya yetki sorunu).",
     "Dokümanı yeniden yükleyin ve analizi tekrar başlatın; yetki hatasında uygulama klasörünün yazılabilir olduğunu doğrulayın."),
    ("dokuman", r"pdf|docx|görsel|image|unsupported.?(file|format)|desteklenmeyen|encrypted|şifreli|boş doküman|metin çıkarılamadı",
     "Doküman okunamadı",
     "Yüklenen doküman işlenemedi — görsel/taranmış PDF (CLI modunda desteklenmez), şifreli dosya veya boş içerik olabilir.",
     "Metin tabanlı PDF/DOCX/MD kullanın; taranmış belge için önce OCR uygulayın."),
    ("json", r"jsondecodeerror|expecting value|unterminated string|invalid json|json.?parse|boş yanıt|result' alanı boş",
     "Model yanıtı işlenemedi",
     "Claude'dan gelen yanıt beklenen biçimde değildi (kesilmiş ya da boş yanıt).",
     "Genellikle geçicidir — 'Yeniden Başlat' ile tekrar deneyin; sürerse Bağlam Filtresi'ni daraltın."),
    ("alt_surec", r"alt süreç hata kodu|exit code|returned non-zero|beklenmeyen hata",
     "Analiz süreci beklenmedik şekilde sonlandı",
     "Arka plandaki analiz süreci hata koduyla kapandı; ayrıntı aşağıdaki teknik izde ve `logs/app.log`'da.",
     "'Yeniden Başlat' ile tekrar deneyin; tekrarlanıyorsa teknik izi ekip lideriyle paylaşın."),
]


def _ilk_satir(ham: str) -> str:
    """Traceback'i at, analist için anlamlı ilk satırı bırak (en fazla 200 karakter)."""
    metin = (ham or "").strip()
    metin = re.split(r"\n\s*Traceback \(most recent call last\)", metin, maxsplit=1)[0]
    satir = next((s.strip() for s in metin.splitlines() if s.strip()), "")
    return satir[:200]


def insanlastir(ham: str | None) -> dict | None:
    """Ham hata metnini analist-dostu yapıya çevirir; ham None/boş ise None."""
    if not ham or not str(ham).strip():
        return None
    ham = str(ham)
    cf = ham.casefold()
    for kategori, desen, baslik, aciklama, oneri in _KURALLAR:
        if re.search(desen, cf):
            return {"kategori": kategori, "baslik": baslik, "aciklama": aciklama, "oneri": oneri,
                    "ozet": _ilk_satir(ham), "ham": ham}
    return {"kategori": "bilinmeyen", "baslik": _ilk_satir(ham) or "Bilinmeyen hata",
            "aciklama": "Sınıflandırılamayan bir hata oluştu; teknik ayrıntı aşağıda.",
            "oneri": "'Yeniden Başlat' ile tekrar deneyin; sürerse teknik izi ekip lideriyle paylaşın.",
            "ozet": _ilk_satir(ham), "ham": ham}
