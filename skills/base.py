"""
Ortak altyapı: dosya okuma, API çağrısı, bağlam filtresi, yardımcılar.
Tüm skill modülleri buradan import eder.
"""

import os
import re
import sys
import base64
import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

USE_CLAUDE_CLI = os.getenv("USE_CLAUDE_CLI", "false").lower() in ("1", "true", "yes")

if not USE_CLAUDE_CLI:
    try:
        import anthropic
    except ImportError:
        print("HATA: anthropic paketi yüklü değil. pip install anthropic")
        sys.exit(1)

try:
    import fitz
    PYMUPDF_VAR = True
except ImportError:
    PYMUPDF_VAR = False

try:
    from docx import Document as DocxDocument
    DOCX_VAR = True
except ImportError:
    DOCX_VAR = False

# ─── Dizinler ────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent.parent
INPUT_DIR   = BASE_DIR / "input"
OUTPUT_DIR  = BASE_DIR / "output"
REF_DIR     = BASE_DIR / "reference"
UI_CODE_DIR = REF_DIR / "ui-code"
CONF_DIR    = REF_DIR / "confluence"
JIRA_REF_DIR = REF_DIR / "jira"
SERVIS_DIR  = REF_DIR / "services"
CONTEXT_FILTER_PATH = REF_DIR / "context_filter.json"

# ─── Model & Limitler ────────────────────────────────────────────────────────

MODEL_ANALIZ = "claude-sonnet-4-6"

MAX_CHARS_BRD     = 100_000
MAX_CHARS_GENEL   =  30_000
MAX_CHARS_UI      =  10_000
MAX_CHARS_UI_TOT  =  60_000
MAX_CHARS_REF     =  15_000
MAX_CHARS_REF_TOT =  50_000

MAX_TOKENS_UZUN     =  8_000
MAX_TOKENS_KISA     =  3_000
MAX_TOKENS_COMBINED = 16_000   # teknik analiz: DDL + OpenAPI YAML içerdiği için yüksek
MAX_TOKENS_BRD_CMB  =  9_000
MAX_TOKENS_KAPSAM   =  8_000

# ─── Prompt Yönetimi ─────────────────────────────────────────────────────────

PROMPTS_PATH = REF_DIR / "prompts.json"

# Varsayılan sistem prompt içerikleri (skill başına düzenlenebilir bölüm)
VARSAYILAN_PROMPTLAR: dict[str, dict] = {
    "surec_analizi": {
        "ad": "Süreç Analizi",
        "aciklama": "Belgeyi analiz eden iş analisti rolü ve çıktı bölümleri.",
        "icerik": (
            "Deneyimli iş analisti olarak verilen belgeyi TÜMÜYLE analiz et "
            "(çok sayfalı olsa bile tüm içeriği değerlendir). Türkçe Markdown:\n\n"
            "## 1. Süreç Özeti\n"
            "## 2. Aktörler ve Roller\n"
            "## 3. Süreç Adımları\n"
            "## 4. Sistemler ve Entegrasyonlar\n"
            "## 5. İş Kuralları\n"
            "## 6. Riskler ve Belirsizlikler\n"
            "## 7. Analist Notları\n\n"
            "## EK KURALLAR — v3.1.1 PATCH: Kaynak Önceliği ve Çakışma Yönetimi\n\n"
            "Birden fazla referans aynı bilgi için farklı değerler içerdiğinde, aşağıdaki ÖNCELİK SIRASINI uygula:\n\n"
            "**Öncelik Sırası (yüksek → düşük):**\n"
            "1. **Swagger / API Dokümantasyonu** — Endpoint isimleri, request/response şeması, HTTP status'lar\n"
            "2. **Mevcut Teknik Dokümantasyon (Confluence)** — Mimari kararlar, sistem dokümantasyonu\n"
            "3. **BRD** — İş gereksinimleri, ekran tanımları, kabul kriterleri\n"
            "4. **Jira Task İçerikleri** — Geçmiş geliştirme kararları\n"
            "5. **UI Index / UI Kodu (Metadata)** — Mevcut frontend yapısı\n\n"
            "**Çakışma Tespit Kuralı:**\n"
            "Aynı entity için iki kaynak ÇELİŞEN bilgi içeriyorsa:\n"
            "1. Yüksek öncelikli kaynağı kullan (ana metin)\n"
            "2. Çakışmayı \"Karar Bekleyen Konular\" bölümüne MUTLAKA taşı:\n\n"
            "| # | Konu | Durum | Notlar |\n"
            "|---|------|-------|--------|\n"
            "| N | [Entity] — kaynak çakışması | ⚠️ Çelişki | [Kaynak A]: [değer A] / [Kaynak B]: [değer B] — [Yüksek öncelikli] tercih edildi |\n\n"
            "**Sessiz Birleştirme YASAK:** Çakışan değerleri gizlice birleştirmek yasak. Çakışma her zaman raporlanmalı.\n\n"
            "## EK KURALLAR — v3.1.1 PATCH: Kaynak İzleme Kuralı\n\n"
            "Çıktıdaki HER somut iddia (alan, kural, hata mesajı, endpoint, validasyon) en az BİR kaynağa dayanmalı.\n\n"
            "**Görünür Çıktı Etkisi (minimal):**\n"
            "- Tablolardaki ana içerik DEĞİŞMEZ\n"
            "- Her tablonun ÜSTÜNE 1 satır eklenir: `> Kaynak: [BRD §X.Y / Swagger / Confluence / Jira / UI]`\n\n"
            "**Bilinmeyen / Türetilen Bilgi:** Sentez ile üretilen bölümler için:\n"
            "`> Kaynak: 🔍 Türetilmiş (BRD §X.Y bağlamından çıkarıldı)`\n\n"
            "**Tamamen Kaynaksız İddialar YASAK:** Hiçbir kaynakta olmayan ve türetilemeyen alan/kural "
            "ana çıktıya eklenmez — \"Karar Bekleyen Konular\" bölümüne taşınır."
        ),
    },
    "teknik_analiz_bolumler": {
        "ad": "Teknik Analiz — Bölümler",
        "aciklama": "Teknik analiz raporunun bölüm yapısı (1–11). Bölüm 12 UI kodu varsa otomatik eklenir.",
        "icerik": (
            "## 1. Teknik Özet\n"
            "2-3 paragraf: projenin teknik kapsamı, kritik kararlar, öne çıkan riskler.\n\n"
            "## 2. Sistem Mimarisi ve Bileşenler\n"
            "- Katmanlar (Frontend / Backend / DB / 3rd-party) ve aralarındaki ilişkiler\n"
            "- Her bileşen için: teknoloji seçimi + gerekçe\n"
            "- Deployment mimarisi (monolith / microservice / serverless vb.)\n\n"
            "## 3. Veri Modeli ve Akışı\n"
            "Her tablo için gerçek DDL yaz. Örnek format:\n\n"
            "```sql\n"
            "CREATE TABLE ornek_tablo (\n"
            "    id          BIGSERIAL PRIMARY KEY,\n"
            "    alan_adi    VARCHAR(255) NOT NULL,\n"
            "    olusturuldu TIMESTAMPTZ  NOT NULL DEFAULT NOW()\n"
            ");\n"
            "CREATE INDEX idx_ornek_alan ON ornek_tablo(alan_adi);\n"
            "```\n\n"
            "- Tablo ilişkileri (FK) ve kısıtlar dahil\n"
            "- Veri akışı: hangi servis hangi tabloyu yazar/okur\n\n"
            "## 4. API ve Entegrasyon Tasarımı\n"
            "Her endpoint için OpenAPI 3.0 formatında YAML bloğu yaz. Örnek:\n\n"
            "```yaml\n"
            "/api/v1/ornek:\n"
            "  post:\n"
            "    summary: Örnek endpoint\n"
            "    requestBody:\n"
            "      content:\n"
            "        application/json:\n"
            "          schema:\n"
            "            type: object\n"
            "            required: [alan]\n"
            "            properties:\n"
            "              alan: {type: string}\n"
            "    responses:\n"
            "      '200':\n"
            "        description: Başarılı\n"
            "        content:\n"
            "          application/json:\n"
            "            schema:\n"
            "              type: object\n"
            "              properties:\n"
            "                id: {type: integer}\n"
            "      '400': {description: Geçersiz istek}\n"
            "      '401': {description: Yetkisiz}\n"
            "```\n\n"
            "- Mevcut referans dosyalarındaki gerçek endpoint'leri kullan, uydurma\n"
            "- Auth yöntemi (Bearer / API Key / Cookie) belirt\n\n"
            "## 5. İş Mantığı ve Kurallar\n"
            "- Kritik iş akışları adım adım (numbered list)\n"
            "- Validation kuralları ve edge case'ler\n"
            "- State machine varsa durum geçişlerini göster\n\n"
            "## 6. Güvenlik ve Yetkilendirme\n"
            "- Auth/authz mekanizması (JWT, OAuth2, RBAC vb.)\n"
            "- Hassas veri (PII, ödeme) işleme yaklaşımı\n"
            "- Güvenlik kontrol listesi (rate limiting, CSRF, XSS, SQL injection koruması)\n\n"
            "## 7. Performans ve Ölçeklenebilirlik\n"
            "- Beklenen yük (RPS, concurrent user, veri hacmi)\n"
            "- Darboğaz noktaları ve çözümler (cache, index, async işlem)\n"
            "- Horizontal/vertical scaling stratejisi\n\n"
            "## 8. Hata Yönetimi ve Dayanıklılık\n"
            "- Hata kodları ve anlamları (tablo formatında)\n"
            "- Retry / circuit breaker / fallback stratejileri\n"
            "- Kritik servis kesintisi senaryoları\n\n"
            "## 9. Test Stratejisi\n"
            "- Unit / integration / e2e test kapsamı\n"
            "- Kritik test senaryoları (happy path + edge case'ler)\n"
            "- Test araçları ve ortamı\n\n"
            "## 10. Teknik Riskler ve Öneriler\n"
            "| Risk | Olasılık | Etki | Öneri |\n"
            "|------|----------|------|-------|\n"
            "| ...  | Y/O/D    | Y/O/D| ...   |\n\n"
            "## 11. Uygulama Yol Haritası\n"
            "Öncelik sırasına göre aşamalar (Sprint/Milestone bazlı):\n"
            "- **Aşama 1:** ...\n"
            "- **Aşama 2:** ...\n\n"
            "## EK KURALLAR — v3.1.1 PATCH: Kaynak Önceliği ve Çakışma Yönetimi\n\n"
            "Birden fazla referans aynı bilgi için farklı değerler içerdiğinde, aşağıdaki ÖNCELİK SIRASINI uygula:\n\n"
            "**Öncelik Sırası (yüksek → düşük):**\n"
            "1. **Swagger / API Dokümantasyonu** — Endpoint isimleri, request/response şeması, HTTP status'lar\n"
            "2. **Mevcut Teknik Dokümantasyon (Confluence)** — Mimari kararlar, sistem dokümantasyonu\n"
            "3. **BRD** — İş gereksinimleri, ekran tanımları, kabul kriterleri\n"
            "4. **Jira Task İçerikleri** — Geçmiş geliştirme kararları\n"
            "5. **UI Index / UI Kodu (Metadata)** — Mevcut frontend yapısı\n\n"
            "**Çakışma Tespit Kuralı:**\n"
            "Aynı entity için iki kaynak ÇELİŞEN bilgi içeriyorsa:\n"
            "1. Yüksek öncelikli kaynağı kullan (ana metin)\n"
            "2. Çakışmayı \"Karar Bekleyen Konular\" bölümüne MUTLAKA taşı:\n\n"
            "| # | Konu | Durum | Notlar |\n"
            "|---|------|-------|--------|\n"
            "| N | [Entity] — kaynak çakışması | ⚠️ Çelişki | [Kaynak A]: [değer A] / [Kaynak B]: [değer B] — [Yüksek öncelikli] tercih edildi |\n\n"
            "**Sessiz Birleştirme YASAK:** Çakışan değerleri gizlice birleştirmek yasak. Çakışma her zaman raporlanmalı.\n\n"
            "## EK KURALLAR — v3.1.1 PATCH: Kaynak İzleme Kuralı\n\n"
            "Çıktıdaki HER somut iddia (alan, kural, hata mesajı, endpoint, validasyon) en az BİR kaynağa dayanmalı.\n\n"
            "**Görünür Çıktı Etkisi (minimal):**\n"
            "- Tablolardaki ana içerik DEĞİŞMEZ\n"
            "- Her tablonun ÜSTÜNE 1 satır eklenir: `> Kaynak: [BRD §X.Y / Swagger / Confluence / Jira / UI]`\n\n"
            "**Bilinmeyen / Türetilen Bilgi:** Sentez ile üretilen bölümler için:\n"
            "`> Kaynak: 🔍 Türetilmiş (BRD §X.Y bağlamından çıkarıldı)`\n\n"
            "**Tamamen Kaynaksız İddialar YASAK:** Hiçbir kaynakta olmayan ve türetilemeyen alan/kural "
            "ana çıktıya eklenmez — \"Karar Bekleyen Konular\" bölümüne taşınır.\n\n"
            "## EK KURALLAR — v3.1.1 PATCH: Halüsinasyon Koruması (Entity Whitelist)\n\n"
            "**Whitelist Kuralı:** Aşağıdaki entity tipleri için yalnızca referanslarda GERÇEKTEN GEÇEN değerleri kullan:\n\n"
            "| Entity Tipi | İzin Verilen Kaynak | Yasak |\n"
            "|-------------|--------------------|-------|\n"
            "| **API Endpoint** (path) | Swagger, Confluence, Jira | Uydurmak |\n"
            "| **DB Tablo / Kolon Adı** | Confluence DB şeması, mevcut DDL, Swagger response | Uydurmak |\n"
            "| **Rol Adı / Yetki Adı** | BRD veya UI Index `roles` listesi | Varsayım yapmak |\n"
            "| **Route Path** | UI Index `routes` listesi | Uydurmak |\n"
            "| **Bileşen Adı** | UI Index `component` / `shared_components` | Uydurmak |\n"
            "| **Yetki Resource:Action** | BRD veya mevcut RBAC dokümantasyonu | \"MODULE_X:WRITE\" şeklinde uydurmak |\n\n"
            "**Doğrulama Akışı:** Entity referanslarda geçiyor mu? → Evet: kullan. "
            "Hayır, türetilebilir mi? → Evet: `🔍 Türetilmiş` etiketiyle + Karar Bekleyen'e ekle. "
            "Hayır: kullanma, soru olarak Karar Bekleyen'e taşı.\n\n"
            "**Sentez İzni:** Standart RESTful isimlendirme (GET/POST/PUT/DELETE /api/v1/[kaynak]) için sentez izinli — "
            "ancak `[kaynak]` adı yalnızca referanslarda geçen domain isminden türetilebilir.\n\n"
            "**Doğrulama Listesi:** Türetilmiş entity'leri Karar Bekleyen Konular sonuna ekle:\n"
            "`> **Türetilmiş Entity'ler (Doğrulanması Gerekenler):** [entity] — 🔍 Türetilmiş ([kaynak bağlamı])`"
        ),
    },
    "teknik_analiz_rol": {
        "ad": "Teknik Analiz — Rol ve Kurallar",
        "aciklama": "Claude'un teknik analistik rolü, bağlam kullanım kuralları ve dikkat edilecek noktalar.",
        "icerik": (
            "Kıdemli yazılım mimarı olarak süreç analizini teknik perspektiften değerlendir.\n\n"
            "**Bağlam Kullanımı:**\n"
            "- Referans dosyalar (Confluence, Swagger, Jira): Gerçek endpoint ve tablo adlarını buradan al — uydurma\n"
            "- Mevcut UI kodu: Bölüm 12 için mevcut ekranları ve gerekli değişiklikleri çıkar\n"
            "- HTML prototip: Bölüm 12'de prototipdeki bileşenleri ve UX kararlarını teknik analize yansıt\n\n"
            "**Dikkat Edilecekler:**\n"
            "- Bölüm 3 ve 4 için çalışan kod örnekleri (SQL DDL ve OpenAPI YAML) üret — "
            "soyut açıklama değil, doğrudan kullanılabilir çıktı bekleniyor\n"
            "- Referans dosyalarda gerçek endpoint veya tablo bilgisi varsa onları kullan\n"
            "- Tüm metinler Türkçe; teknik terimler (API, DDL, endpoint) İngilizce kalabilir"
        ),
    },
    "teknik_analiz_sorular": {
        "ad": "Teknik Analiz — Soru Formatı",
        "aciklama": "Açık sorular bölümündeki her sorunun yapısı ve doldurulacak alanlar.",
        "icerik": (
            "### S[N]: [Başlık]\n"
            "- **Kategori:** Teknik/İş Kuralı/Entegrasyon/Güvenlik/Veri/UX\n"
            "- **Öncelik:** Kritik/Yüksek/Orta/Düşük\n"
            "- **Soru:** ...\n"
            "- **Bağlam:** Hangi bölüm/kararı etkiliyor\n"
            "- **Etki:** Yanıt alınmadan ilerlenemeyecek kısım"
        ),
    },
    "brd_analizi_rol": {
        "ad": "BRD Analizi — Rol ve Kurallar",
        "aciklama": "Claude'un BRD analistlik rolü ve dikkat edilecek noktalar.",
        "icerik": (
            "Kıdemli ürün ve iş analisti olarak BRD dokümanını TAMAMIYLA analiz et "
            "(çok sayfalı olsa bile tüm bölümleri oku).\n\n"
            "**Bağlam Kullanımı:**\n"
            "- BRD dokümanındaki her bölümü, gereksinimi ve kısıtı kaydet\n"
            "- Referans materyallerle çapraz kontrol yap, çelişkileri raporla\n"
            "- Eksik ya da belirsiz gereksinimleri sorular bölümünde detaylandır\n\n"
            "**Dikkat Edilecekler:**\n"
            "- Product Owner bakış açısından değerlendir\n"
            "- Fonksiyonel ve fonksiyonel olmayan gereksinimleri ayrı listele\n"
            "- Kabul kriterlerinin test edilebilir olduğunu kontrol et\n"
            "- Tüm metinler Türkçe"
        ),
    },
    "brd_analizi_sorular": {
        "ad": "BRD Analizi — Soru Formatı",
        "aciklama": "PO sorular bölümündeki her sorunun yapısı.",
        "icerik": (
            "### S[N]: [Başlık]\n"
            "- **Bölüm:** BRD bölüm adı\n"
            "- **Öncelik:** Kritik/Yüksek/Orta\n"
            "- **Soru:** ...\n"
            "- **Mevcut Durum:** ...\n"
            "- **Beklenen Yanıt:** ..."
        ),
    },
    "brd_analizi_bolumler": {
        "ad": "BRD Analizi — Bölümler",
        "aciklama": "BRD analiz raporu bölümleri ve PO soru formatı.",
        "icerik": (
            "## 1. BRD Özeti\n"
            "## 2. Fonksiyonel Gereksinimler\n"
            "## 3. Fonksiyonel Olmayan Gereksinimler\n"
            "## 4. Paydaşlar ve Kullanıcı Hikayeleri\n"
            "## 5. Kabul Kriterleri\n"
            "## 6. Bağımlılıklar ve Kısıtlar\n"
            "## 7. Kapsam Dışı\n"
            "## 8. Eksiklikler ve Tutarsızlıklar"
        ),
    },
    "kapsam_analizi_rol": {
        "ad": "Kapsam Analizi — Rol ve Kurallar",
        "aciklama": "Claude'un iki BRD versiyonunu karşılaştırırken üstlendiği rol ve dikkat noktaları.",
        "icerik": (
            "Kıdemli ürün ve iş analisti olarak iki BRD versiyonunu karşılaştır.\n\n"
            "**Bağlam Kullanımı:**\n"
            "- Mevcut BRD (referans): Temel alınan orijinal doküman\n"
            "- Revize BRD (yüklenen): Değerlendirilen yeni versiyon\n"
            "- Mevcut UI kodu (varsa): Her alternatif için UI etkisini değerlendir\n\n"
            "**Dikkat Edilecekler:**\n"
            "- Kapsam genişlemesi ile daralmayı açıkça ayırt et\n"
            "- Risk analizinde tahmini geliştirme etkisini belirt\n"
            "- Alternatifler gerçekçi ve uygulanabilir olmalı\n"
            "- Tüm metinler Türkçe"
        ),
    },
    "kapsam_analizi_alternatifler": {
        "ad": "Kapsam Analizi — Alternatif Formatı",
        "aciklama": "Her alternatif sürecin bölüm yapısı.",
        "icerik": (
            "## Alternatif [N]: [İsim]\n"
            "### Yaklaşım\n"
            "### Avantajlar\n"
            "### Dezavantajlar\n"
            "### Uygun Olduğu Durumlar\n"
            "### Uygulama Karmaşıklığı"
        ),
    },
    "kapsam_analizi_bolumler": {
        "ad": "Kapsam Analizi — Bölümler",
        "aciklama": "İki BRD karşılaştırma raporu bölümleri.",
        "icerik": (
            "## 1. Özet Değişiklikler\n"
            "## 2. Yeni Eklenen Gereksinimler\n"
            "## 3. Kaldırılan Gereksinimler\n"
            "## 4. Değiştirilen Gereksinimler\n"
            "## 5. Kapsam Etkisi\n"
            "## 6. Risk Analizi\n\n"
            "## EK KURALLAR — v3.1.1 PATCH: Kaynak Önceliği ve Çakışma Yönetimi\n\n"
            "Birden fazla referans aynı bilgi için farklı değerler içerdiğinde, aşağıdaki ÖNCELİK SIRASINI uygula:\n\n"
            "**Öncelik Sırası (yüksek → düşük):**\n"
            "1. **Swagger / API Dokümantasyonu** — Endpoint isimleri, request/response şeması, HTTP status'lar\n"
            "2. **Mevcut Teknik Dokümantasyon (Confluence)** — Mimari kararlar, sistem dokümantasyonu\n"
            "3. **BRD** — İş gereksinimleri, ekran tanımları, kabul kriterleri\n"
            "4. **Jira Task İçerikleri** — Geçmiş geliştirme kararları\n"
            "5. **UI Index / UI Kodu (Metadata)** — Mevcut frontend yapısı\n\n"
            "**Çakışma Tespit Kuralı:**\n"
            "Aynı entity için iki kaynak ÇELİŞEN bilgi içeriyorsa:\n"
            "1. Yüksek öncelikli kaynağı kullan (ana metin)\n"
            "2. Çakışmayı \"Karar Bekleyen Konular\" bölümüne MUTLAKA taşı:\n\n"
            "| # | Konu | Durum | Notlar |\n"
            "|---|------|-------|--------|\n"
            "| N | [Entity] — kaynak çakışması | ⚠️ Çelişki | [Kaynak A]: [değer A] / [Kaynak B]: [değer B] — [Yüksek öncelikli] tercih edildi |\n\n"
            "**Sessiz Birleştirme YASAK:** Çakışan değerleri gizlice birleştirmek yasak. Çakışma her zaman raporlanmalı."
        ),
    },
    "html_mockup_base": {
        "ad": "HTML Prototip",
        "aciklama": "Prototip üretici rolü ve çıktı gereksinimleri.",
        "icerik": (
            "Deneyimli UI/UX tasarımcısı ve frontend geliştirici olarak süreç analizi "
            "dokümanından çalışan bir HTML prototipi oluştur.\n\n"
            "Gereksinimler:\n"
            "- Tek HTML dosyası (CSS ve JS gömülü); dış CDN kullanabilirsin\n"
            "- Süreç analizindeki tüm ana ekranlar/adımlar gezinilebilir olmalı\n"
            "- Gerçekçi form alanları, butonlar ve örnek veri gösterimi\n"
            "- Sidebar veya tab ile ekranlar arası geçiş\n"
            "- Türkçe UI metinleri, profesyonel görünüm\n"
            "- Tıklanabilir butonlar çalışsın; formlar submit'te sonuç göstersin"
        ),
    },
    "jira_tasks": {
        "ad": "Jira Task Hiyerarşisi",
        "aciklama": "Epic/Story/Subtask üretici rolü ve kuralları.",
        "icerik": (
            "Kıdemli yazılım mimarısın. Teknik analiz dokümanından Jira task hiyerarşisi üret.\n\n"
            "Kurallar:\n"
            "- 1 Epic: tüm projeyi kapsayan üst başlık\n"
            "- 3-7 Story: her biri bağımsız bir fonksiyonel alan (BE, FE, entegrasyon, vb.)\n"
            "- Her Story için 2-4 Subtask: somut, ölçülebilir geliştirme adımları\n"
            "- Her Story için 2-5 acceptance_criteria: test edilebilir kabul kriteri\n"
            "- Tüm metinler Türkçe; teknik terimler (API, endpoint, vb.) İngilizce kalabilir\n\n"
            "Yanıtı SADECE aşağıdaki XML+JSON formatında ver:\n\n"
            "<jira_hierarchy>\n"
            "{\n"
            '  "epic_summary": "...",\n'
            '  "epic_description": "...",\n'
            '  "stories": [\n'
            "    {\n"
            '      "summary": "...",\n'
            '      "description": "...",\n'
            '      "acceptance_criteria": ["...", "..."],\n'
            '      "subtasks": [\n'
            '        {"summary": "...", "description": "..."}\n'
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "</jira_hierarchy>\n\n"
            "## EK KURALLAR — v3.1.1 PATCH: Halüsinasyon Koruması (Entity Whitelist)\n\n"
            "**Whitelist Kuralı:** Aşağıdaki entity tipleri için yalnızca referanslarda GERÇEKTEN GEÇEN değerleri kullan:\n\n"
            "| Entity Tipi | İzin Verilen Kaynak | Yasak |\n"
            "|-------------|--------------------|-------|\n"
            "| **API Endpoint** (path) | Swagger, Confluence, Jira | Uydurmak |\n"
            "| **DB Tablo / Kolon Adı** | Confluence DB şeması, mevcut DDL, Swagger response | Uydurmak |\n"
            "| **Rol Adı / Yetki Adı** | BRD veya UI Index `roles` listesi | Varsayım yapmak |\n"
            "| **Route Path** | UI Index `routes` listesi | Uydurmak |\n"
            "| **Bileşen Adı** | UI Index `component` / `shared_components` | Uydurmak |\n"
            "| **Yetki Resource:Action** | BRD veya mevcut RBAC dokümantasyonu | \"MODULE_X:WRITE\" şeklinde uydurmak |\n\n"
            "**Doğrulama Akışı:** Entity referanslarda geçiyor mu? → Evet: kullan. "
            "Hayır, türetilebilir mi? → Evet: `🔍 Türetilmiş` etiketiyle + description'a not düş. "
            "Hayır: kullanma, summary'de \"[Doğrulama gerekli]\" ile işaretle.\n\n"
            "**Sentez İzni:** Standart RESTful isimlendirme için sentez izinli — "
            "ancak `[kaynak]` adı yalnızca referanslarda geçen domain isminden türetilebilir."
        ),
    },
    "refine": {
        "ad": "Refine (Yeniden Çalıştır)",
        "aciklama": "Düzeltme notlarına göre mevcut çıktıyı günceller. {duzeltme_notu} ve {mevcut_cikti} yer tutucuları zorunludur.",
        "icerik": (
            "Mevcut analiz çıktısını düzeltme notlarına göre güncelle. Belirtilmeyen bölümleri değiştirme.\n\n"
            "### Düzeltme Notları\n"
            "{duzeltme_notu}\n\n"
            "### Mevcut Çıktı\n"
            "{mevcut_cikti}\n\n"
            "Önce güncellenmiş Markdown içeriğini ver. Ardından, Markdown içeriğinin hemen sonuna "
            "(boş satır ile ayrılmış) aşağıdaki bloğu MUTLAKA ekle:\n\n"
            "<changed_sections>\n"
            "{{\n"
            "  \"changedSections\": [\n"
            "    {{\n"
            "      \"section\": \"[Bölüm adı veya başlık + satır referansı]\",\n"
            "      \"changeType\": \"added|updated|removed\",\n"
            "      \"reason\": \"[Düzeltme notunun hangi maddesinden geldiği — özet 1 cümle]\"\n"
            "    }}\n"
            "  ]\n"
            "}}\n"
            "</changed_sections>\n\n"
            "Hiç değişiklik yapılmadıysa `\"changedSections\": []`. "
            "`changeType` yalnızca `added` / `updated` / `removed` olabilir."
        ),
    },
    "confluence_publisher": {
        "ad": "Confluence Publisher",
        "aciklama": "Markdown analiz dokümanını Confluence Storage Format (XHTML) ve metadata JSON'a dönüştürür.",
        "icerik": (
            "## ROL\n"
            "Kıdemli content publishing mühendisisin. Confluence Storage Format (XHTML-based) ve "
            "markdown-to-confluence dönüşümü konusunda uzmansın. Çıktıların kurumsal wiki'lerde "
            "düzgün render olur, navigasyona uygun ve aranabilir.\n\n"
            "## GÖREV\n"
            "Sağlanan Markdown analiz dökümanını Confluence Storage Format'a dönüştür. "
            "Sayfa metadata'sını üret (parent, labels, attachments).\n\n"
            "## KESİN KURALLAR\n"
            "1. **Markdown İÇERİĞİNİ KORU** — anlam ve yapı değişmemeli, sadece format dönüşümü\n"
            "2. **Confluence-specific bileşenleri kullan:**\n"
            "   - Tablolar: native `<table><tbody><tr><th>/<td>` (Confluence Tables Macro değil)\n"
            "   - Kod blokları: `<ac:structured-macro ac:name=\"code\">` + dil parametresi + `<ac:plain-text-body>`\n"
            "   - Bilgi kutuları: `<ac:structured-macro ac:name=\"info\">` / `warning` / `note`\n"
            "   - Toggle başlıklar: `<ac:structured-macro ac:name=\"expand\">` (uzun bölümler için)\n"
            "3. **Başlık seviyesi haritalama:**\n"
            "   - Markdown `# H1` → Sayfa başlığı (metadata'da, içerikte değil)\n"
            "   - Markdown `## H2` → `<h2>` (Confluence için en üst içerik başlığı)\n"
            "   - Markdown `### H3` → `<h3>`\n"
            "4. **Link normalleştirme:** `[text](url)` → `<a href=\"url\">text</a>`\n"
            "5. **Çıktıyı 2 XML bloğu halinde ver** (aşağıdaki ÇIKTI FORMATI'na göre)\n\n"
            "## ÇIKTI FORMATI\n\n"
            "YALNIZCA aşağıdaki XML bloklarını üret. Öncesinde / sonrasında metin OLMAMALI:\n\n"
            "<confluence_metadata>\n"
            "{\n"
            "  \"page_title\": \"[H1 başlığı]\",\n"
            "  \"parent_page_id\": null,\n"
            "  \"parent_page_title\": \"[Opsiyonel — orchestrator dolduracak]\",\n"
            "  \"space_key\": \"[Confluence space key — orchestrator dolduracak]\",\n"
            "  \"labels\": [\"analysis\", \"[modul-adi]\"],\n"
            "  \"attachments\": [],\n"
            "  \"version_comment\": \"[Orchestrator'dan: 'İlk yayın' vb.]\"\n"
            "}\n"
            "</confluence_metadata>\n\n"
            "<confluence_storage>\n"
            "[Confluence Storage Format XHTML içeriği]\n"
            "</confluence_storage>\n\n"
            "## DÖNÜŞÜM HARİTASI\n\n"
            "| Markdown | Confluence Storage |\n"
            "|----------|-------------------|\n"
            "| `# H1` | Metadata `page_title` (içerik DEĞİL) |\n"
            "| `## H2` | `<h2>` |\n"
            "| `### H3` | `<h3>` |\n"
            "| `**bold**` | `<strong>bold</strong>` |\n"
            "| `*italic*` | `<em>italic</em>` |\n"
            "| `` `code` `` | `<code>code</code>` |\n"
            "| ` ```lang\\ncode\\n``` ` | `<ac:structured-macro ac:name=\"code\">...` |\n"
            "| `- bullet` | `<ul><li>bullet</li></ul>` |\n"
            "| `1. numbered` | `<ol><li>numbered</li></ol>` |\n"
            "| `[text](url)` | `<a href=\"url\">text</a>` |\n"
            "| `> Kaynak: BRD §X` | `<ac:structured-macro ac:name=\"info\">...` |\n"
            "| Table (pipe) | `<table><tbody><tr><th>...` |\n\n"
            "## YASAKLAR\n"
            "- Markdown içeriğinin ANLAMINI değiştirmek (sadeleştirme, çevirme, özetleme)\n"
            "- Tabloları liste / liste'leri tablo yapmak — yapısal sadakat zorunlu\n"
            "- Confluence-spesifik olmayan HTML kullanmak\n"
            "- Metadata bloğunu boş bırakmak — minimum `page_title` + `labels` zorunlu\n"
            "- İçeriğe orchestrator için yorum eklemek — temiz XHTML üret"
        ),
    },
}


def prompt_yukle(skill_id: str) -> str:
    """Özelleştirilmiş prompt varsa onu, yoksa varsayılanı döndür."""
    try:
        if PROMPTS_PATH.exists():
            data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
            if skill_id in data:
                return data[skill_id]
    except Exception:
        pass
    return VARSAYILAN_PROMPTLAR[skill_id]["icerik"]


def prompt_kaydet(skill_id: str, icerik: str) -> None:
    """Prompt özelleştirmesini prompts.json'a kaydet."""
    try:
        data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8")) if PROMPTS_PATH.exists() else {}
    except Exception:
        data = {}
    data[skill_id] = icerik
    PROMPTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def prompt_sifirla(skill_id: str) -> None:
    """Özelleştirmeyi sil, varsayılana dön."""
    try:
        data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8")) if PROMPTS_PATH.exists() else {}
    except Exception:
        return
    data.pop(skill_id, None)
    PROMPTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extended_thinking_acik() -> bool:
    return os.getenv("EXTENDED_THINKING", "false").lower() in ("1", "true", "yes")

UI_UZANTILAR = {
    ".tsx", ".jsx", ".ts", ".js", ".mjs", ".cjs",
    ".vue", ".svelte",
    ".html", ".css", ".scss", ".less",
    ".yml", ".yaml", ".json",
}


# ─── Metin Yardımcıları ───────────────────────────────────────────────────────

def _xml_ayir(text: str, tag: str) -> str:
    m = re.search(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _metin_sikistir(metin: str) -> str:
    return re.sub(r'\n{3,}', '\n\n', metin).strip()


def _metin_kes(metin: str, limit: int, dosya_adi: str) -> str:
    if len(metin) <= limit:
        return metin
    satirlar = metin.splitlines()
    sonuc, toplam, kesilen = [], 0, False
    for satir in satirlar:
        uzunluk = len(satir) + 1
        if satir.startswith("#"):
            sonuc.append(satir)
            toplam += uzunluk
            continue
        if toplam + uzunluk > limit:
            kesilen = True
            break
        sonuc.append(satir)
        toplam += uzunluk
    cikti = "\n".join(sonuc)
    if kesilen:
        cikti += f"\n\n[... {dosya_adi} kısaltıldı: orijinal {len(metin):,} karakter, gönderilen {len(cikti):,} karakter ...]"
    return cikti


# ─── Dosya Okuma ──────────────────────────────────────────────────────────────

def pdf_oku(path: Path) -> str:
    if not PYMUPDF_VAR:
        return f"[PDF okuma hatası: PyMuPDF yüklü değil — {path.name}]"
    try:
        doc = fitz.open(str(path))
        parcalar = []
        for i, page in enumerate(doc):
            metin = page.get_text()
            if metin.strip():
                parcalar.append(f"<!-- Sayfa {i+1} -->\n{metin}")
        return "\n".join(parcalar)
    except Exception as e:
        return f"[PDF okuma hatası: {e}]"


def docx_oku(path: Path) -> str:
    if not DOCX_VAR:
        return f"[DOCX okuma hatası: python-docx yüklü değil — {path.name}]"
    try:
        doc = DocxDocument(str(path))
        parcalar = []
        for para in doc.paragraphs:
            stil = para.style.name
            metin = para.text.strip()
            if not metin:
                continue
            if "Heading 1" in stil or "Title" in stil:
                parcalar.append(f"\n# {metin}")
            elif "Heading 2" in stil:
                parcalar.append(f"\n## {metin}")
            elif "Heading 3" in stil:
                parcalar.append(f"\n### {metin}")
            elif "Heading 4" in stil:
                parcalar.append(f"\n#### {metin}")
            else:
                parcalar.append(metin)
        for tablo in doc.tables:
            satirlar = []
            for i, satir in enumerate(tablo.rows):
                hucreler = [h.text.strip().replace("\n", " ") for h in satir.cells]
                satirlar.append(" | ".join(hucreler))
                if i == 0:
                    satirlar.append(" | ".join(["---"] * len(hucreler)))
            if satirlar:
                parcalar.append("\n" + "\n".join(satirlar))
        return "\n\n".join(parcalar)
    except Exception as e:
        return f"[DOCX okuma hatası: {e}]"


def gorsel_hazirla(path: Path) -> dict:
    suffix = path.suffix.lower()
    mt = "image/png" if suffix == ".png" else "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}}


def dosya_oku(path: Path, limit: int = MAX_CHARS_GENEL) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        metin = pdf_oku(path)
    elif suffix == ".docx":
        metin = docx_oku(path)
    else:
        metin = path.read_text(encoding="utf-8", errors="replace")
    return _metin_kes(metin, limit, path.name)


def input_hazirla(is_brd: bool = False) -> tuple[list, str]:
    dosyalar = sorted(
        f for f in INPUT_DIR.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    if not dosyalar:
        raise FileNotFoundError("input/ klasöründe dosya yok.")
    dosya = dosyalar[0]
    suffix = dosya.suffix.lower()
    limit = MAX_CHARS_BRD if is_brd else MAX_CHARS_GENEL
    if suffix in (".png", ".jpg", ".jpeg", ".webp"):
        parcalar = [
            gorsel_hazirla(dosya),
            {"type": "text", "text": f"Yukarıdaki görsel: {dosya.name}"},
        ]
    else:
        metin = dosya_oku(dosya, limit)
        parcalar = [{"type": "text", "text": f"### {dosya.name}\n\n{metin}"}]
    return parcalar, dosya.name


def referans_brd_oku() -> str | None:
    brd_dir = REF_DIR / "current-brd"
    dosyalar = sorted(brd_dir.glob("*")) if brd_dir.exists() else []
    dosyalar = [f for f in dosyalar if f.is_file() and not f.name.startswith(".")]
    if not dosyalar:
        return None
    parcalar = []
    for f in dosyalar:
        metin = dosya_oku(f, MAX_CHARS_BRD)
        parcalar.append(f"### {f.name}\n\n{metin}")
    return "\n\n---\n\n".join(parcalar)


# ─── UI Kodu ──────────────────────────────────────────────────────────────────

def ui_kodu_hazirla() -> str | None:
    if not UI_CODE_DIR.exists():
        return None
    CONFIG_UZANTILAR = {".json", ".yml", ".yaml"}
    MAX_CHARS_CONFIG = 5_000
    dosyalar = sorted(
        f for f in UI_CODE_DIR.rglob("*")
        if f.is_file() and not f.name.startswith(".")
        and f.suffix.lower() in UI_UZANTILAR
    )
    if not dosyalar:
        return None
    parcalar, toplam = [], 0
    for f in dosyalar:
        if toplam >= MAX_CHARS_UI_TOT:
            parcalar.append(f"\n[... toplam UI kodu limiti aşıldı, {f.name} ve sonrası dahil edilmedi ...]")
            break
        try:
            metin = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        limit = MAX_CHARS_CONFIG if f.suffix.lower() in CONFIG_UZANTILAR else MAX_CHARS_UI
        metin = _metin_kes(metin, limit, f.name)
        goreceli = f.relative_to(UI_CODE_DIR)
        uzanti = f.suffix.lstrip(".")
        blok = f"### {goreceli}\n```{uzanti}\n{metin}\n```"
        parcalar.append(blok)
        toplam += len(blok)
    return "\n\n".join(parcalar) if parcalar else None


def ui_dosyalari_listele() -> list[dict]:
    if not UI_CODE_DIR.exists():
        return []
    sonuc = []
    for f in sorted(UI_CODE_DIR.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        if f.suffix.lower() not in UI_UZANTILAR:
            continue
        goreceli = f.relative_to(UI_CODE_DIR)
        klasor = str(goreceli.parent) if goreceli.parent != Path(".") else ""
        sonuc.append({
            "yol": str(goreceli),
            "ad": f.name,
            "klasor": klasor,
            "boyut": f.stat().st_size,
            "uzanti": f.suffix.lower(),
        })
    return sonuc


# ─── Bağlam Filtresi ──────────────────────────────────────────────────────────

def load_context_filter() -> dict | None:
    if CONTEXT_FILTER_PATH.exists():
        try:
            return json.loads(CONTEXT_FILTER_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _filtrele_openapi_json(json_path: Path, keywords: list) -> "Path | None | bool":
    try:
        spec = json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
        paths = spec.get("paths", {})
        if not paths or len(paths) < 10:
            return None
        eslesen = {}
        for path_key, path_obj in paths.items():
            pl = path_key.lower()
            esl = any(kw in pl for kw in keywords)
            if not esl:
                for method, op in path_obj.items():
                    if not isinstance(op, dict):
                        continue
                    metin = (op.get("summary", "") + " " + op.get("description", "") +
                             " " + " ".join(op.get("tags", []))).lower()
                    if any(kw in metin for kw in keywords):
                        esl = True
                        break
            if esl:
                eslesen[path_key] = path_obj
        if not eslesen:
            return False
        if len(eslesen) >= len(paths) * 0.7:
            return None
        kw_hash = hashlib.md5(",".join(sorted(keywords)).encode()).hexdigest()[:8]
        tmp_dir = REF_DIR / "_filtered_cache"
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"_filtered_{json_path.stem}_{kw_hash}.json"
        if tmp_path.exists() and tmp_path.stat().st_mtime >= json_path.stat().st_mtime:
            return tmp_path
        filtered_spec = {
            "info": spec.get("info", {}),
            "_not": f"{len(paths)} endpoint'ten {len(eslesen)} tanesi filtrelendi (keywords: {keywords})",
            "paths": eslesen,
        }
        tmp_path.write_text(json.dumps(filtered_spec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   🔍 {json_path.name}: {len(paths)} → {len(eslesen)} endpoint filtrelendi")
        return tmp_path
    except Exception:
        return None


def filtrele_referanslar(all_files: list, ctx: dict) -> list:
    keywords  = [k.strip().lower() for k in ctx.get("keywords", [])         if k.strip()]
    jira_keys = [k.strip().upper() for k in ctx.get("jira_keys", [])        if k.strip()]
    conf_pages = [p.strip().lower() for p in ctx.get("confluence_pages", []) if p.strip()]

    if not keywords and not jira_keys and not conf_pages:
        return all_files

    filtered = []
    jira_issues_combined = {}

    for f in all_files:
        try:
            rel = str(f.relative_to(REF_DIR)).replace("\\", "/")
        except ValueError:
            filtered.append(f)
            continue

        if rel.startswith("services/"):
            if f.name.startswith("_"):
                continue
            if f.suffix.lower() == ".json" and keywords:
                result = _filtrele_openapi_json(f, keywords)
                filtered.append(result if (result and result is not False) else f)
            else:
                filtered.append(f)
            continue

        if rel.startswith("confluence/"):
            include = False
            fname_l = f.stem.lower().replace("-", " ")
            if conf_pages:
                include = any(p in fname_l or fname_l in p for p in conf_pages)
            elif keywords:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore").lower()
                    include = any(kw in content for kw in keywords)
                except Exception:
                    pass
            if not include and jira_keys:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore").upper()
                    include = any(jk in content for jk in jira_keys)
                except Exception:
                    pass
            if include:
                filtered.append(f)
            continue

        if rel.startswith("jira/") and f.suffix == ".json" and not f.name.startswith("_"):
            try:
                issues = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
                if not isinstance(issues, list):
                    filtered.append(f)
                    continue
                matched = []
                for issue in issues:
                    if jira_keys and issue.get("key", "").upper() in jira_keys:
                        matched.append(issue)
                        continue
                    if keywords:
                        text = (str(issue.get("summary", "")) + " " +
                                str(issue.get("description", ""))).lower()
                        if any(kw in text for kw in keywords):
                            matched.append(issue)
                if matched:
                    jira_issues_combined[f.stem] = matched
            except Exception:
                filtered.append(f)
            continue

        if f.name.startswith("_") or f.name == "context_filter.json":
            continue

        if f.suffix.lower() == ".json" and keywords:
            result = _filtrele_openapi_json(f, keywords)
            if result is not False and result is not None:
                filtered.append(result)
            elif result is None:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore").lower()
                    if any(kw in content or kw in f.name.lower() for kw in keywords):
                        filtered.append(f)
                except Exception:
                    filtered.append(f)
            continue

        if keywords:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore").lower()
                if any(kw in content or kw in f.name.lower() for kw in keywords):
                    filtered.append(f)
            except Exception:
                filtered.append(f)
        else:
            filtered.append(f)

    if jira_issues_combined:
        tmp = JIRA_REF_DIR / "_context_filtered.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        combined = []
        for proj, issues in jira_issues_combined.items():
            for issue in issues:
                issue["_project"] = proj
                combined.append(issue)
        tmp.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
        filtered.append(tmp)

    return filtered


def referans_dosyalari_hazirla() -> list[Path]:
    uzantilar = ["*.md", "*.txt", "*.pdf", "*.html", "*.json", "*.yaml", "*.yml"]
    tum_dosyalar: list[Path] = []
    for dizin in [CONF_DIR, JIRA_REF_DIR, SERVIS_DIR]:
        if dizin.exists():
            for u in uzantilar:
                tum_dosyalar.extend(f for f in dizin.rglob(u) if f.is_file() and not f.name.startswith("_"))
    if not tum_dosyalar:
        return []
    ctx = load_context_filter()
    if ctx:
        filtreli = filtrele_referanslar(tum_dosyalar, ctx)
        aktif = []
        if ctx.get("keywords"):
            aktif.append(f"kelime:{','.join(ctx['keywords'])}")
        if ctx.get("jira_keys"):
            aktif.append(f"jira:{','.join(ctx['jira_keys'])}")
        if ctx.get("confluence_pages"):
            aktif.append(f"conf:{','.join(ctx['confluence_pages'])}")
        if aktif:
            print(f"🔍 Bağlam filtresi: {' | '.join(aktif)}")
            print(f"   {len(tum_dosyalar)} → {len(filtreli)} referans dosya")
        return filtreli
    return tum_dosyalar


# ─── API Çağrısı ──────────────────────────────────────────────────────────────

def _mesajlari_birlestir(sistem: str, mesajlar: list) -> str:
    parcalar = [sistem, "\n\n" + "─" * 60 + "\n"]
    for m in mesajlar:
        icerik = m.get("content", [])
        if isinstance(icerik, str):
            parcalar.append(icerik)
        elif isinstance(icerik, list):
            for p in icerik:
                if isinstance(p, dict) and p.get("type") == "text":
                    parcalar.append(p["text"])
    return "\n\n".join(parcalar)


def _api_cagri_cli(sistem: str, mesajlar: list) -> str:
    claude_yolu = shutil.which("claude")
    if not claude_yolu:
        raise EnvironmentError(
            "'claude' komutu PATH'te bulunamadı. Claude Code CLI kurulu ve aktif olmalı."
        )
    tam_prompt = _mesajlari_birlestir(sistem, mesajlar)
    cli_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run(
        [claude_yolu, "-p", "--output-format", "text"],
        input=tam_prompt,
        capture_output=True,
        text=True,
        timeout=600,
        env=cli_env,
    )
    if proc.returncode != 0:
        hata_detay = proc.stderr.strip() or proc.stdout.strip() or "Bilinmeyen hata"
        raise RuntimeError(f"claude CLI hatası (kod {proc.returncode}): {hata_detay}")
    yanit = proc.stdout.strip()
    if not yanit:
        raise RuntimeError("claude CLI boş yanıt döndürdü.")
    return yanit


def _api_cagri_direct(
    sistem: str,
    mesajlar: list,
    model: str,
    max_tokens: int,
    thinking: bool = False,
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY .env dosyasında tanımlı değil.")
    client = anthropic.Anthropic(api_key=api_key)

    if thinking:
        budget = min(max_tokens // 2, 10_000)
        yanit = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "enabled", "budget_tokens": budget},
            system=sistem,
            messages=mesajlar,
        )
        return "\n".join(b.text for b in yanit.content if b.type == "text")

    yanit = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": sistem, "cache_control": {"type": "ephemeral"}}],
        messages=mesajlar,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    )
    return yanit.content[0].text


def _api_cagri(
    sistem: str,
    mesajlar: list,
    model: str = MODEL_ANALIZ,
    max_tokens: int = MAX_TOKENS_UZUN,
    thinking: bool = False,
) -> str:
    if USE_CLAUDE_CLI:
        return _api_cagri_cli(sistem, mesajlar)
    return _api_cagri_direct(sistem, mesajlar, model, max_tokens, thinking=thinking)


def _kaydet(dosya_adi: str, icerik: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yol = OUTPUT_DIR / dosya_adi
    yol.write_text(icerik, encoding="utf-8")
    print(f"✓ Kaydedildi: {yol}")
    return yol


# ─── Yeniden Çalıştır ────────────────────────────────────────────────────────

YENIDEN_CALISTIR_PROMPT = """Mevcut analiz çıktısını düzeltme notlarına göre güncelle. Belirtilmeyen bölümleri değiştirme.

### Düzeltme Notları
{duzeltme_notu}

### Mevcut Çıktı
{mevcut_cikti}

Önce güncellenmiş Markdown içeriğini ver. Ardından, Markdown içeriğinin hemen sonuna (boş satır ile ayrılmış) aşağıdaki bloğu MUTLAKA ekle:

<changed_sections>
{{
  "changedSections": [
    {{
      "section": "[Bölüm adı veya başlık + satır referansı]",
      "changeType": "added|updated|removed",
      "reason": "[Düzeltme notunun hangi maddesinden geldiği — özet 1 cümle]"
    }}
  ]
}}
</changed_sections>

Hiç değişiklik yapılmadıysa `"changedSections": []`. `changeType` yalnızca `added` / `updated` / `removed` olabilir."""


def yeniden_calistir(hedef_dosya: str, duzeltme_notu: str) -> Path:
    print(f"Yeniden çalıştırılıyor: {hedef_dosya}")
    yol = OUTPUT_DIR / hedef_dosya
    if not yol.exists():
        raise FileNotFoundError(f"{hedef_dosya} bulunamadı.")
    mevcut = dosya_oku(yol, MAX_CHARS_BRD)
    sistem = prompt_yukle("refine").format(
        duzeltme_notu=duzeltme_notu,
        mevcut_cikti=mevcut,
    )
    mesajlar = [{"role": "user", "content": [
        {"type": "text", "text": "Düzeltme notlarını uygula ve çıktıyı yeniden üret."}
    ]}]
    yanit = _api_cagri(sistem, mesajlar)
    return _kaydet(hedef_dosya, yanit)
