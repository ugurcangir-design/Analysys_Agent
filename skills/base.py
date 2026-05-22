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
MAX_CHARS_REF     =  15_000   # dosya başına limit
MAX_CHARS_REF_TOT =  50_000   # geriye dönük uyumluluk — yeni kod per-tip limitleri kullanır

# Kaynak tipine göre karakter limitleri — prompt cache ile ilk çağrıda maliyet çıkar,
# sonraki 5dk içindeki çağrılarda ~%90 tasarruf.
MAX_CHARS_CONF_TOT   =  80_000   # Confluence sayfaları toplamı
MAX_CHARS_JIRA_TOT   =  60_000   # Jira issue'ları toplamı (markdown formatında)
MAX_CHARS_SERVIS_TOT =  60_000   # Swagger/OpenAPI toplamı
MAX_CHARS_DIGER_TOT  =  20_000   # Diğer referanslar toplamı

MAX_TOKENS_UZUN     =  8_000
MAX_TOKENS_KISA     =  3_000
MAX_TOKENS_COMBINED = 16_000   # teknik analiz: DDL + OpenAPI YAML içerdiği için yüksek
MAX_TOKENS_BRD_CMB  =  9_000
MAX_TOKENS_KAPSAM   =  8_000

# ─── Prompt Yönetimi ─────────────────────────────────────────────────────────

PROMPTS_PATH = REF_DIR / "prompts.json"

# Ortak EK KURALLAR sabiti — tekrarlayan bloğu tek yerde tut.
# prompt_yukle() bu sabitler içeriklerini belirli skill_id'lere otomatik ekler.
_ORTAK_EK_KURALLAR = (
    "\n\n## EK KURALLAR — Kaynak Önceliği ve Çakışma Yönetimi\n\n"
    "Birden fazla referans aynı bilgi için farklı değerler içerdiğinde, aşağıdaki ÖNCELİK SIRASINI uygula:\n\n"
    "**Öncelik Sırası (yüksek → düşük):**\n"
    "1. **Swagger / OpenAPI** — Endpoint, request/response şeması, HTTP status\n"
    "2. **Confluence Teknik Dokümantasyon** — Mimari kararlar, sistem dokümantasyonu\n"
    "3. **BRD / Süreç Analizi** — İş gereksinimleri, ekran tanımları, kabul kriterleri\n"
    "4. **Jira Task İçerikleri** — Geçmiş geliştirme kararları\n"
    "5. **UI Kodu** — Mevcut frontend yapısı\n\n"
    "**Çakışma Tespit Kuralı:**\n"
    "Aynı entity için iki kaynak ÇELİŞEN bilgi içeriyorsa:\n"
    "1. Yüksek öncelikli kaynağı kullan (ana metin)\n"
    "2. Çakışmayı \"Açık Sorular / Karar Bekleyen Konular\" bölümüne MUTLAKA taşı:\n\n"
    "| # | Konu | Durum | Notlar |\n"
    "|---|------|-------|--------|\n"
    "| N | [Entity] — kaynak çakışması | ⚠️ Çelişki | [Kaynak A]: [değer A] / [Kaynak B]: [değer B] — [Yüksek öncelikli] tercih edildi |\n\n"
    "**Sessiz Birleştirme YASAK:** Çakışan değerleri gizlice birleştirmek yasak. Çakışma her zaman raporlanmalı.\n\n"
    "## EK KURALLAR — Kaynak İzleme (Source Attribution)\n\n"
    "Çıktıdaki HER somut iddia (alan, kural, endpoint, hata kodu, validasyon, tablo satırı) "
    "için kaynak işaretle. **Bu kural zorunludur ve atlanırsa rapor eksik sayılır.**\n\n"
    "**Format (kısa, satır içi):**\n"
    "- Tablo başına 1 satır: `> Kaynak: [BRD §X.Y / Swagger:dosya.json / Confluence:sayfa.md / Jira:KEY-123 / UI:route]`\n"
    "- Tablo SATIRI içinde tek hücre: son sütun `Kaynak` olabilir → `[BRD §X.Y]` / `[Türetilmiş]` / `[❓ Belirsiz]`\n"
    "- Paragraf içinde kritik iddia: cümle sonuna `[K: BRD §X.Y]`\n\n"
    "**Kaynak Etiketleri:**\n"
    "- `[K: BRD §X.Y]` — BRD/süreç analizinde açıkça geçiyor\n"
    "- `[K: Swagger:dosya.json#/endpoint]` — Swagger'da var\n"
    "- `[K: Confluence:sayfa]` — Confluence sayfasında geçiyor\n"
    "- `[K: Jira:KEY-123]` — ilgili Jira issue'da var\n"
    "- `[K: UI:components/X.tsx]` — mevcut UI kodunda var\n"
    "- `[K: 🔍 Türetilmiş - <kaynak bağlamı>]` — kaynaktan dolaylı çıkarsama\n"
    "- `[K: ❓ Belirsiz]` — hiçbir kaynakta YOK; MUTLAKA Açık Sorular'a taşı\n\n"
    "**Tamamen Kaynaksız İddialar YASAK:** Hiçbir kaynakta olmayan ve türetilemeyen alan/kural "
    "ana çıktıya GİRMEZ — Açık Sorular bölümüne soru olarak taşınır.\n\n"
    "## EK KURALLAR — Halüsinasyon Koruması (Entity Whitelist)\n\n"
    "**Whitelist Kuralı:** Aşağıdaki entity tipleri için yalnızca referanslarda GERÇEKTEN GEÇEN değerleri kullan:\n\n"
    "| Entity Tipi | İzin Verilen Kaynak | Yasak |\n"
    "|-------------|--------------------|-------|\n"
    "| **API Endpoint (path)** | Swagger, Confluence, Jira | Uydurmak |\n"
    "| **DB Tablo / Kolon** | Confluence DB şeması, mevcut DDL, Swagger response | Uydurmak |\n"
    "| **Rol / Yetki Adı** | BRD, RBAC dokümantasyonu | Varsayım yapmak |\n"
    "| **Route Path** | UI kodu, mevcut sayfa listesi | Uydurmak |\n"
    "| **Bileşen Adı** | UI kodu | Uydurmak |\n"
    "| **Yetki Resource:Action** | BRD veya mevcut RBAC | \"MODULE_X:WRITE\" şeklinde uydurmak |\n"
    "| **Hata Kodu (örn. E2001)** | Mevcut error catalog | Numara uydurmak |\n"
    "| **Tablo/Kolon Tipi (VARCHAR, INT)** | Mevcut DDL / Swagger şeması | Tip varsayımı |\n\n"
    "**Doğrulama Akışı:**\n"
    "1. Entity referanslarda geçiyor mu? → Evet: kullan, `[K: <kaynak>]` ekle\n"
    "2. Hayır, kaynaktan türetilebilir mi? → Evet: `[K: 🔍 Türetilmiş - <bağlam>]` etiketi + Açık Sorular'a doğrulama notu\n"
    "3. Hayır: kullanma → Açık Sorular'a soru olarak taşı\n\n"
    "**Sentez İzni:** Standart RESTful isimlendirme (GET/POST/PUT/DELETE /api/v1/[kaynak]) için sentez izinli — "
    "ancak `[kaynak]` adı yalnızca referanslarda geçen domain isminden türetilebilir.\n\n"
    "## EK KURALLAR — İzlenebilirlik (Traceability)\n\n"
    "Süreç analizinde tanımlanan ID'leri (BR-XXX, AC-XXX, PA-XXX, EF-XXX, AF-XXX) teknik analiz "
    "ve sonraki çıktılarda referans olarak kullan:\n"
    "- DDL/API/iş mantığı bölümlerinde hangi BR-ID'yi karşıladığını belirt\n"
    "- Test senaryolarında hangi AC-ID'yi doğruladığını belirt\n"
    "- Çıktının sonuna **İzlenebilirlik Matrisi** ekle: BR-ID/AC-ID → Hangi modül/bölüm/test"
)

# Bu skill_id'lere prompt_yukle() otomatik olarak _ORTAK_EK_KURALLAR ekler
_EK_KURAL_SKILL_IDS = frozenset({
    "surec_analizi",
    "teknik_analiz_bolumler",
    "kapsam_analizi_bolumler",
    "brd_analizi_bolumler",
    "jira_tasks",
})

# Varsayılan sistem prompt içerikleri (skill başına düzenlenebilir bölüm)
VARSAYILAN_PROMPTLAR: dict[str, dict] = {
    "surec_analizi_rol": {
        "ad": "Süreç Analizi — Rol ve Kurallar",
        "aciklama": "Süreç analistinin rolü, bağlam kullanım kuralları ve çıktı kalite hedefi.",
        "icerik": (
            "Kıdemli iş ve süreç analisti olarak verilen dokümanı (BRD / iş tanımı / süreç tarifi) "
            "TÜMÜYLE analiz et. Çıktın şu hedefi karşılamalı:\n\n"
            "🎯 **Hedef:** Bu süreç analizi doğrudan teknik analiz için TEK KAYNAK olarak kullanılacak. "
            "Geliştirici ve mimar bu dokümanı okuyarak DDL, API, iş mantığı ve test senaryolarını "
            "üretebilmeli. Bu yüzden eksiklik, belirsizlik ve varsayım yasaktır — her şey AÇIK olmalı.\n\n"
            "**Bağlam Kullanımı (öncelik sırası):**\n"
            "- **Birincil kaynak:** Input dokümanı (BRD / süreç tarifi) — atlama yok, her satır okunmalı\n"
            "- **Swagger/OpenAPI (YÜKSEK ÖNCELİK):** Mevcut endpoint adları, path'ler, şemalar — "
            "burada geçen servisler süreç adımlarında ve Bölüm 8 entegrasyon tablosunda kullanılmalı\n"
            "- **Confluence:** Mimari kararlar, DB şeması, RBAC, mevcut süreç dokümantasyonu\n"
            "- **Jira task geçmişi:** Geçmiş geliştirme kararları; çelişen karar Açık Sorular'a\n"
            "- **Mevcut UI kodu (varsa):** Hangi ekranlar/akışlar zaten var, hangileri yeni\n"
            "- **Çakışma varsa:** Yüksek öncelikli kaynağı kullan + Açık Sorular'a not düş\n\n"
            "**Dikkat Edilecekler:**\n"
            "- Belirsiz ifade (\"genelde\", \"muhtemelen\", \"sistem otomatik\") → soru olarak kayıt al\n"
            "- Her aktör, rol, adım, kural NUMARALI ID ile etiketle (A-001, BR-001, PA-001 vb.)\n"
            "- Edge case ve hata akışlarını AÇIKÇA soru sor — \"hata olursa ne olur?\"\n"
            "- Kabul kriterlerini test edilebilir biçimde yaz (Given/When/Then)\n"
            "- Tüm metinler Türkçe; teknik terimler (API, endpoint) İngilizce kalabilir"
        ),
    },
    "surec_analizi": {
        "ad": "Süreç Analizi — Bölümler",
        "aciklama": "Süreç analizi raporu bölüm yapısı. Teknik analize kaynak oluşturacak detay seviyesi.",
        "icerik": (
            "Çıktı Türkçe Markdown formatında olmalı. Aşağıdaki bölümler ZORUNLU:\n\n"
            "## 1. Süreç Özeti\n"
            "- 2-3 paragraf: iş hedefi, etkilenen sistemler, beklenen sonuç\n"
            "- Kapsam ve kapsam dışı 2 maddelik liste\n\n"
            "## 2. Aktörler ve Roller\n"
            "| ID | Aktör/Rol | Tip | Sorumluluk | Yetki Düzeyi | Kaynak |\n"
            "|----|-----------|-----|------------|--------------|--------|\n"
            "| A-001 | ... | İç kullanıcı/Dış sistem/Otomatik job | ... | Okuma/Yazma/Onay | [BRD §X] |\n\n"
            "## 3. Süreç Adımları — Happy Path\n"
            "Her adım için: ID, aktör, eylem, girdi, çıktı, kullanılan sistem.\n\n"
            "**PA-001:** [Aktör A-XXX] [eylem] → [çıktı]\n"
            "- Girdi: ...\n"
            "- Çıktı: ...\n"
            "- Sistem/Bileşen: ...\n"
            "- Bağlı kural: BR-XXX\n"
            "- Kaynak: [BRD §X.Y]\n\n"
            "(Adım sırası NUMARALI olmalı; karar noktalarında alternatif/hata akışına referans ver: → AF-001 / EF-001)\n\n"
            "## 4. Alternatif Akışlar\n"
            "Koşullu dallanmalar (örn. \"kullanıcı VIP ise farklı işlem\"). Her biri AF-001, AF-002 ile.\n\n"
            "**AF-001:** [Koşul] — [Ana akıştan ayrılma noktası: PA-XXX]\n"
            "- Tetikleyici koşul: ...\n"
            "- Adımlar: ...\n"
            "- Ana akışa dönüş noktası: PA-XXX veya süreç sonu\n"
            "- Kaynak: ...\n\n"
            "## 5. Hata / Exception Akışları\n"
            "Her hata senaryosu için: tetikleyici, etki, kullanıcıya gösterilen mesaj, recovery aksiyonu.\n\n"
            "**EF-001:** [Hata Adı] — Tetikleyici adım: PA-XXX\n"
            "- Tetikleyici: ...\n"
            "- Etki (kullanıcı/veri/sistem): ...\n"
            "- Kullanıcı mesajı: \"...\"\n"
            "- Recovery: Otomatik retry / Manuel müdahale / Rollback / Loglama\n"
            "- Bağlı validasyon: BR-XXX\n"
            "- Kaynak: ...\n\n"
            "## 6. İş Kuralları\n"
            "| ID | Kural | Tip | Etkilenen Adım | Doğrulama Anı | Hata Senaryosu | Kaynak |\n"
            "|----|-------|-----|----------------|---------------|----------------|--------|\n"
            "| BR-001 | ... | Validasyon/Hesaplama/Yetki/İş Akışı/Süre | PA-XXX | İstemci/Sunucu/Async | EF-XXX | [BRD §X] |\n\n"
            "(Her kural test edilebilir olmalı — \"sistem hızlı olmalı\" YASAK; \"yanıt 200ms altında\" geçerli)\n\n"
            "## 7. Veri Varlıkları (Kavramsal)\n"
            "Tablolar veya DDL değil — entity ve ana özelliklerin kavramsal listesi. Teknik analiz bu "
            "listeden DDL üretecek.\n\n"
            "| Entity | Ana Özellikler | Yaşam Döngüsü | İlişkili Entity'ler | Kaynak |\n"
            "|--------|----------------|---------------|---------------------|--------|\n"
            "| ... | ad, durum, oluşturulma vb. | Oluştur → ... → Arşiv | ... | [BRD §X] |\n\n"
            "## 8. Sistemler ve Entegrasyonlar\n"
            "| Sistem | Tip | Yön | Tetikleyici | Veri Alışverişi | Kaynak |\n"
            "|--------|-----|-----|-------------|-----------------|--------|\n"
            "| ... | İç/Dış/3rd-party | Inbound/Outbound/Bidirectional | Olay/Zamanlı/Manuel | ... | [Swagger:...] |\n\n"
            "## 9. Karar Tabloları (varsa)\n"
            "Birden çok koşulun farklı aksiyona yol açtığı durumlar için.\n\n"
            "| Koşul 1 | Koşul 2 | ... | Aksiyon | Bağlı Adım |\n"
            "|---------|---------|-----|---------|------------|\n"
            "| Evet | Hayır | ... | ... | PA-XXX |\n\n"
            "## 10. Kabul Kriterleri (Üst Seviye)\n"
            "Test edilebilir, Given/When/Then formatında. Her AC bir süreç davranışını doğrular.\n\n"
            "**AC-001:** [Başlık]\n"
            "- **Given:** [Başlangıç durumu]\n"
            "- **When:** [Tetikleyici aksiyon — PA-XXX]\n"
            "- **Then:** [Beklenen sonuç — gözlemlenebilir]\n"
            "- Bağlı kural: BR-XXX\n"
            "- Kaynak: [BRD §X.Y]\n\n"
            "## 11. Açık Sorular / Karar Bekleyen Konular\n"
            "| # | Konu | Tip | Önem | Bağlı Bölüm | Mevcut Durum | Beklenen Yanıt |\n"
            "|---|------|-----|------|-------------|--------------|----------------|\n"
            "| Q-001 | ... | Çelişki/Eksik/Belirsiz | Kritik/Yüksek/Orta | BR-XXX | [Mevcut bilgi] | [Ne sorulduğu] |\n\n"
            "(Belirsiz tüm konuları buraya taşı. Belirsizlikleri ana metne sızdırma.)\n\n"
            "## 12. İzlenebilirlik / Kaynak Matrisi\n"
            "| Bölüm | Birincil Kaynak | Destekleyici Kaynaklar | Türetilmiş İçerik |\n"
            "|-------|------------------|------------------------|--------------------|\n"
            "| 3. Süreç Adımları | BRD §3 | Confluence:X | PA-005 (türetildi) |"
        ),
    },
    "teknik_analiz_bolumler": {
        "ad": "Teknik Analiz — Bölümler",
        "aciklama": "Teknik analiz raporu bölüm yapısı. Geliştirme ekibi bu çıktıdan doğrudan kod yazabilmeli.",
        "icerik": (
            "🎯 **Çıktı Hedefi:** Geliştirici bu dokümanı okuyarak DDL'i çalıştırabilmeli, "
            "OpenAPI YAML'ı import edebilmeli, validation kurallarını kodlayabilmeli, "
            "test senaryolarını yazabilmeli. Eksik veya muğlak alan YASAK.\n\n"
            "## 1. Teknik Özet\n"
            "- 2-3 paragraf: projenin teknik kapsamı, kritik kararlar, öne çıkan riskler\n"
            "- Karşılanan süreç ID'leri (özet): BR-001..BR-NN, AC-001..AC-NN, PA-001..PA-NN\n\n"
            "## 2. Sistem Mimarisi ve Bileşenler\n"
            "- Katmanlar (Frontend / Backend / DB / 3rd-party) ve aralarındaki ilişkiler\n"
            "- Her bileşen için: teknoloji seçimi + gerekçe + kaynak\n"
            "- Deployment mimarisi (monolith / microservice / serverless vb.)\n"
            "- Component diagram (mermaid blok önerilir):\n"
            "```mermaid\ngraph LR\n  FE[Frontend] --> BFF[BFF/API Gateway]\n  BFF --> SVC[Service]\n  SVC --> DB[(DB)]\n```\n\n"
            "## 3. Veri Modeli ve Akışı\n"
            "Her tablo için gerçek DDL yaz. Mevcut DDL referansta varsa ONU kullan.\n\n"
            "```sql\n"
            "CREATE TABLE ornek_tablo (\n"
            "    id          BIGSERIAL PRIMARY KEY,\n"
            "    alan_adi    VARCHAR(255) NOT NULL,\n"
            "    durum       VARCHAR(20)  NOT NULL DEFAULT 'AKTIF',\n"
            "    olusturuldu TIMESTAMPTZ  NOT NULL DEFAULT NOW(),\n"
            "    guncellendi TIMESTAMPTZ  NOT NULL DEFAULT NOW(),\n"
            "    CONSTRAINT chk_durum CHECK (durum IN ('AKTIF','PASIF','SILINDI'))\n"
            ");\n"
            "CREATE INDEX idx_ornek_alan ON ornek_tablo(alan_adi);\n"
            "```\n\n"
            "- FK ilişkileri (ON DELETE/UPDATE davranışı dahil)\n"
            "- Index stratejisi (sorgu paterni → index)\n"
            "- Veri akışı tablosu: hangi servis hangi tabloyu yazar/okur\n"
            "- Soft delete / audit kolonları stratejisi\n"
            "- **Karşılanan iş kuralları:** BR-XXX, BR-YYY → hangi tablo/kolon\n\n"
            "## 4. API ve Entegrasyon Tasarımı\n"
            "Her endpoint için OpenAPI 3.0 YAML. Mevcut Swagger referansta varsa ONU baz al, "
            "yeni endpoint ekliyorsan aynı stilde devam ettir.\n\n"
            "```yaml\n"
            "/api/v1/ornek:\n"
            "  post:\n"
            "    summary: Örnek kayıt oluşturma\n"
            "    operationId: createOrnek\n"
            "    security:\n"
            "      - bearerAuth: []\n"
            "    requestBody:\n"
            "      required: true\n"
            "      content:\n"
            "        application/json:\n"
            "          schema:\n"
            "            type: object\n"
            "            required: [alan]\n"
            "            properties:\n"
            "              alan: {type: string, minLength: 1, maxLength: 255}\n"
            "    responses:\n"
            "      '201': {description: Oluşturuldu, content: {application/json: {schema: {$ref: '#/components/schemas/Ornek'}}}}\n"
            "      '400': {description: Validation hatası, content: {application/json: {schema: {$ref: '#/components/schemas/Error'}}}}\n"
            "      '401': {description: Yetkisiz}\n"
            "      '403': {description: Yetersiz yetki}\n"
            "      '409': {description: Çakışan kayıt}\n"
            "      '422': {description: İş kuralı ihlali}\n"
            "```\n\n"
            "- Auth yöntemi (Bearer/API Key/Cookie) belirt — security scheme tanımı\n"
            "- Rate limiting kuralları (endpoint × limit/dakika)\n"
            "- Idempotency key gerektiren endpoint'ler işaretle\n"
            "- **Karşılanan iş kuralları:** her endpoint hangi BR-XXX'i karşılıyor\n\n"
            "## 5. Validation Kuralları (Alan Bazlı Matris)\n"
            "Frontend ve backend'in AYNI kuralı uygulayabilmesi için tek bir kaynak.\n\n"
            "| BR-ID | Endpoint/Form | Alan | Kural | Hata Kodu | Hata Mesajı (TR) | Doğrulama Anı | Kaynak |\n"
            "|-------|---------------|------|-------|-----------|------------------|---------------|--------|\n"
            "| BR-001 | POST /api/v1/X | email | regex e-posta + max 255 | E_VAL_001 | \"Geçerli e-posta giriniz.\" | Client + Server | [BRD §X] |\n\n"
            "(Her validation kuralı bir BR'a bağlı olmalı; bağlı değilse Karar Bekleyen'e taşı)\n\n"
            "## 6. İş Mantığı ve Durum Geçişleri\n"
            "- Kritik akışlar adım adım (PA-XXX referansıyla)\n"
            "- State machine (varsa) mermaid ile:\n"
            "```mermaid\nstateDiagram-v2\n  [*] --> Taslak\n  Taslak --> Onayda: gonder()\n  Onayda --> Onayli: onayla()\n  Onayda --> Taslak: reddet()\n```\n"
            "- **Transaction Sınırları:** hangi işlem atomik (BEGIN..COMMIT), hangileri saga/eventual consistency\n"
            "- **Idempotency:** retry-safe endpoint'ler için idempotency-key stratejisi\n"
            "- **Concurrency:** optimistic locking (version kolonu) / pessimistic lock / queue\n\n"
            "## 7. Güvenlik, Yetkilendirme ve Veri Koruması\n"
            "- Auth mekanizması (JWT/OAuth2 detayı; expiry, refresh, signing algoritması)\n"
            "- **Yetki Matrisi:**\n"
            "| Rol | Resource | Action | Şart | Kaynak |\n"
            "|-----|----------|--------|------|--------|\n"
            "| A-001 | Ornek | READ | kendi kaydı | [BRD §X] |\n\n"
            "- PII / hassas veri sınıflandırması (kolon × sınıf × maskeleme stratejisi)\n"
            "- Güvenlik kontrol listesi: rate limiting, CSRF (cookie auth'ta), XSS, SQL injection, IDOR, mass-assignment\n"
            "- Şifreleme: at-rest (TDE/kolon) + in-transit (TLS sürümü)\n\n"
            "## 8. Performans ve Ölçeklenebilirlik\n"
            "- Beklenen yük (RPS, concurrent user, veri hacmi büyümesi/yıl)\n"
            "- SLO/SLA hedefleri (p50/p95/p99 latency, error budget)\n"
            "- Darboğaz noktaları: DB sorgu, dış servis, cache\n"
            "- Cache stratejisi (key, TTL, invalidation)\n"
            "- Horizontal/vertical scaling planı, statelessness kontrolü\n\n"
            "## 9. Hata Yönetimi ve Hata Kodu Katalogu\n"
            "| Kod | HTTP | Tip | Açıklama | Kullanıldığı Endpoint | Kullanıcı Mesajı | Recovery |\n"
            "|-----|------|-----|----------|----------------------|------------------|----------|\n"
            "| E_VAL_001 | 400 | Validation | E-posta formatı geçersiz | POST /api/v1/X | \"Geçerli e-posta giriniz.\" | Kullanıcı düzeltir |\n"
            "| E_BIZ_001 | 422 | İş Kuralı | Limit aşımı | ... | ... | ... |\n"
            "| E_SYS_001 | 500 | Sistem | DB bağlantı kopuk | * | \"Geçici sorun, tekrar deneyin.\" | Retry + circuit breaker |\n\n"
            "- Retry / circuit breaker / fallback / DLQ stratejileri\n"
            "- Tüm hata kodları EF-XXX (süreç) ile eşleştirilmeli\n\n"
            "## 10. Observability — Loglama, Metrik, İz, Alarm\n"
            "- **Loglama:** log level politikası, structured log alanları (trace_id, user_id, action), korelasyon ID\n"
            "- **Metrikler:** business metric (oluşturulan kayıt/saat), tech metric (latency, error rate)\n"
            "- **Dağıtık izleme:** trace context propagation (OpenTelemetry)\n"
            "- **Alarm kuralları:** error rate > %X, latency p95 > Yms\n"
            "- **Audit:** hangi event (kim, ne, ne zaman, hangi kayıt) hangi tabloya yazılır\n\n"
            "## 11. Test Stratejisi\n"
            "- Unit / integration / contract / e2e kapsamı (hedef coverage %)\n"
            "- **Kabul Kriteri → Test Senaryosu eşlemesi:**\n"
            "| AC-ID | Test Adı | Tip | Veri Seti | Beklenen |\n"
            "|-------|----------|-----|-----------|----------|\n"
            "| AC-001 | ... | E2E | ... | ... |\n\n"
            "- Edge case test listesi (her EF-XXX için en az 1 test)\n"
            "- Performance test: hedef RPS + threshold\n"
            "- Test ortamı ve veri yönetimi (fixtures, factory pattern)\n\n"
            "## 12. Teknik Riskler ve Öneriler\n"
            "| Risk | Olasılık | Etki | Tetikleyici | Önlem | Sorumlu | Kaynak |\n"
            "|------|----------|------|-------------|-------|---------|--------|\n"
            "| ...  | Y/O/D    | Y/O/D| ...         | ...   | ...     | ...    |\n\n"
            "## 13. Uygulama Yol Haritası\n"
            "- **Aşama 1 (Temel):** ... — bağımlılık: yok\n"
            "- **Aşama 2 (Genişletme):** ... — bağımlılık: Aşama 1\n"
            "- Migration / rollback stratejisi (DB değişiklikleri için)\n"
            "- Feature flag stratejisi\n\n"
            "## 14. İzlenebilirlik Matrisi (Traceability)\n"
            "Süreç analizindeki her ID'nin teknik analizdeki karşılığı.\n\n"
            "| Süreç ID | Tür | Açıklama (kısa) | Karşılayan Teknik Bölüm | Notlar |\n"
            "|----------|-----|------------------|--------------------------|--------|\n"
            "| BR-001 | İş Kuralı | E-posta zorunlu | §3 Tablo:users, §5 Validation, §11 AC-001 | — |\n"
            "| AC-001 | Kabul Kriteri | Kullanıcı kayıt | §11 Test \"register-happy\" | — |\n"
            "| EF-001 | Hata Akışı | DB hata | §9 E_SYS_001, §11 Test \"db-failure\" | — |\n\n"
            "## 15. Açık Sorular / Karar Bekleyen Konular\n"
            "Süreç analizinden gelen Q-XXX'lar + teknik analizde yeni ortaya çıkan belirsizlikler.\n\n"
            "| # | Konu | Tip | Önem | Bağlı | Beklenen Yanıt | Sorumlu |\n"
            "|---|------|-----|------|-------|----------------|---------|\n"
            "| Q-T-001 | ... | Çelişki/Eksik/Karar | Kritik/Yüksek/Orta | BR-XXX | ... | PO/Mimar/DBA |"
        ),
    },
    "teknik_analiz_rol": {
        "ad": "Teknik Analiz — Rol ve Kurallar",
        "aciklama": "Teknik analistin rolü, bağlam kullanım kuralları ve çıktı kalite hedefi.",
        "icerik": (
            "Kıdemli yazılım mimarı olarak süreç analizini teknik perspektiften değerlendir.\n\n"
            "🎯 **Çıktı Hedefi:** Geliştirme ekibi bu dokümanı okuyarak doğrudan kod yazabilmeli. "
            "DDL çalıştırılabilir, OpenAPI YAML geçerli, validation matrisi frontend ve backend "
            "tarafından implement edilebilir, test senaryoları yazılabilir olmalı.\n\n"
            "**Bağlam Kullanımı (Öncelik Sırası):**\n"
            "1. **Süreç Analizi:** BR-XXX, AC-XXX, PA-XXX, EF-XXX, AF-XXX ID'lerini referans al — "
            "her teknik karar bir süreç ID'sini karşılamalı; izlenebilirlik matrisinde göster\n"
            "2. **Swagger/OpenAPI referansları:** Mevcut endpoint adı, path, response şeması — uydurma\n"
            "3. **Confluence referansları:** Mevcut mimari kararlar, DB şeması, RBAC\n"
            "4. **Jira referansları:** Geçmiş geliştirme kararları (geçmiş kararla çelişme yaratıyorsan açık not düş)\n"
            "5. **HTML prototip:** Bölüm 12'de prototipdeki ekranları, bileşenleri ve UX kararlarını yansıt\n"
            "6. **Mevcut UI kodu:** Bölüm 12 için mevcut ekran/route listesini çıkar\n\n"
            "**Dikkat Edilecekler:**\n"
            "- DDL, OpenAPI YAML, validation matrisi gerçek çalışabilir/import edilebilir olmalı — soyut tarif değil\n"
            "- Referans dosyalarda mevcut entity/endpoint varsa AYNI ismi kullan (yeniden adlandırma yok)\n"
            "- Süreç analizindeki HER BR-XXX, AC-XXX, EF-XXX teknik analizde karşılığını bulmalı; "
            "karşılığı yoksa Açık Sorular'a taşı\n"
            "- Kaynaksız iddia ana metne yazma — Açık Sorular'a taşı\n"
            "- Tüm metinler Türkçe; teknik terimler (API, DDL, endpoint, idempotency) İngilizce kalabilir"
        ),
    },
    "teknik_analiz_sorular": {
        "ad": "Teknik Analiz — Soru Formatı",
        "aciklama": "Açık sorular bölümündeki her sorunun yapısı.",
        "icerik": (
            "### Q-T-[N]: [Başlık]\n"
            "- **Kategori:** Teknik/İş Kuralı/Entegrasyon/Güvenlik/Veri/UX/Performans\n"
            "- **Öncelik:** Kritik/Yüksek/Orta/Düşük\n"
            "- **Bağlı Süreç ID:** BR-XXX / AC-XXX / EF-XXX (varsa)\n"
            "- **Soru:** ...\n"
            "- **Mevcut Bilgi:** Kaynaklarda olan kısım\n"
            "- **Eksik / Çelişen Kısım:** Neden belirsiz\n"
            "- **Beklenen Yanıt:** Hangi formatta cevap gerekiyor (alan tipi/değer kümesi/karar)\n"
            "- **Sorumlu:** PO/Mimar/DBA/SecOps\n"
            "- **Etki:** Yanıt alınmadan ilerlenemeyecek kısım"
        ),
    },
    "brd_analizi_rol": {
        "ad": "BRD Analizi — Rol ve Kurallar",
        "aciklama": "Claude'un BRD analistlik rolü ve dikkat edilecek noktalar.",
        "icerik": (
            "Kıdemli ürün ve iş analisti olarak BRD dokümanını TAMAMIYLA analiz et "
            "(çok sayfalı olsa bile tüm bölümleri oku).\n\n"
            "**Bağlam Kullanımı (öncelik sırası):**\n"
            "- **BRD (birincil):** Her gereksinim, kısıt ve kabul kriteri kaydedilmeli\n"
            "- **Swagger/OpenAPI (varsa):** Mevcut API kapsamını anlayarak teknik uygulanabilirliği değerlendir; "
            "BRD'deki entegrasyon gereksinimlerinin mevcut servislere uygunluğunu kontrol et\n"
            "- **Confluence (varsa):** Mevcut mimari kararlar ve dokümantasyonla çapraz kontrol yap; "
            "BRD ile çelişen sistem kısıtlarını raporla\n"
            "- **Jira task geçmişi (varsa):** İlgili geçmiş görevler ve kararlar var mı? "
            "BRD'deki gereksinimler daha önce analiz edildi mi?\n\n"
            "**Dikkat Edilecekler:**\n"
            "- Product Owner bakış açısından değerlendir\n"
            "- Fonksiyonel ve fonksiyonel olmayan gereksinimleri ayrı listele\n"
            "- Kabul kriterlerinin test edilebilir olduğunu kontrol et\n"
            "- Referanslarla çelişen gereksinimler → Eksiklikler ve Tutarsızlıklar bölümüne\n"
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
            "**Bağlam Kullanımı (öncelik sırası):**\n"
            "- **Mevcut BRD (referans):** Temel alınan orijinal doküman\n"
            "- **Revize BRD (yüklenen):** Değerlendirilen yeni versiyon\n"
            "- **Swagger/OpenAPI (varsa):** Kapsam değişikliklerinin mevcut API'ye etkisini değerlendir; "
            "yeni gereksinimler mevcut servislere uyuyor mu, yeni endpoint gerekiyor mu?\n"
            "- **Confluence (varsa):** Mevcut mimari ve sistem kısıtları kapsam değişikliklerini etkiliyor mu?\n"
            "- **Jira task geçmişi (varsa):** Benzer kapsam değişiklikleri daha önce analiz edildi mi? "
            "Geçmiş kararlardan ders çıkar.\n"
            "- **Mevcut UI kodu (varsa):** Her alternatif için UI etkisini değerlendir\n\n"
            "**Dikkat Edilecekler:**\n"
            "- Kapsam genişlemesi ile daralmayı açıkça ayırt et\n"
            "- Risk analizinde tahmini geliştirme etkisini referanslara dayandır\n"
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
            "## 6. Risk Analizi"
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
            "</jira_hierarchy>"
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
    """Özelleştirilmiş prompt varsa onu, yoksa varsayılanı döndür.

    Belirli skill_id'ler için (_EK_KURAL_SKILL_IDS) içeriğin sonuna otomatik
    olarak _ORTAK_EK_KURALLAR eklenir. Bu sayede kullanıcı editöründe yalnızca
    asıl içerik görünür; tekrarlayan bloklar gizlenir.
    """
    try:
        if PROMPTS_PATH.exists():
            data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
            if skill_id in data:
                icerik = data[skill_id]
                if skill_id in _EK_KURAL_SKILL_IDS:
                    icerik = icerik + _ORTAK_EK_KURALLAR
                return icerik
    except Exception:
        pass
    icerik = VARSAYILAN_PROMPTLAR[skill_id]["icerik"]
    if skill_id in _EK_KURAL_SKILL_IDS:
        icerik = icerik + _ORTAK_EK_KURALLAR
    return icerik


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


# ─── Referans Yardımcıları ───────────────────────────────────────────────────

def _jira_json_to_md(dosya: Path, limit: int) -> str:
    """Jira issue JSON dosyasını kompakt, okunabilir Markdown formatına dönüştürür.

    Ham JSON yerine Markdown kullanmak:
    - Model için daha okunabilir (key, tip, durum, özet ayrık satırlarda)
    - Token olarak daha verimli (~%40 daha az karakter)
    - `[K: Jira:KEY-123]` atıflarını kolaylaştırır
    """
    try:
        issues = json.loads(dosya.read_text(encoding="utf-8", errors="ignore"))
        if not isinstance(issues, list) or not issues:
            return dosya_oku(dosya, limit)
    except Exception:
        return dosya_oku(dosya, limit)

    satirlar: list[str] = []
    toplam = 0
    for idx, issue in enumerate(issues):
        key      = issue.get("key") or (dosya.stem + "-?")
        tip      = issue.get("type", "")
        durum    = issue.get("status", "")
        oncelik  = issue.get("priority", "")
        atanan   = issue.get("assignee", "")
        ozet     = (issue.get("summary") or "").strip()
        aciklama = (issue.get("description") or "").strip()

        meta = " | ".join(p for p in [tip, durum, oncelik] if p)
        satir = f"**{key}**"
        if meta:
            satir += f" [{meta}]"
        if atanan:
            satir += f" — {atanan}"
        satir += f"\n{ozet}"
        if aciklama:
            satir += f"\n{aciklama[:250]}"
        satir += "\n"

        if toplam + len(satir) > limit:
            kalan = len(issues) - idx
            satirlar.append(f"[... +{kalan} issue karakter limiti nedeniyle dahil edilmedi ...]")
            break
        satirlar.append(satir)
        toplam += len(satir)

    return "\n".join(satirlar)


def _ref_bloklari_olustur(ref_dosyalar: list[Path]) -> tuple[list[dict], list[str]]:
    """Referans dosyalarını kaynak tipine göre gruplar, formatlar ve içerik bloklarına dönüştürür.

    Kaynak tipleri ve davranışları:
    - confluence/*.md  → Markdown sayfa metni; MAX_CHARS_CONF_TOT toplam limit
    - jira/*.json      → _jira_json_to_md() ile okunabilir Markdown; MAX_CHARS_JIRA_TOT
    - services/*.json/yaml → OpenAPI/Swagger (bağlam filtresiyle önceden kırpılmış olabilir)
    - diğer            → Ham metin; MAX_CHARS_DIGER_TOT

    Her tip ayrı bir içerik bloğu ve ayrı limit alır.
    cache_control eklenmez — çağıran son stabil bloğa ekler.

    Returns:
        (icerik_bloklari, kullanilan_referanslar):
            icerik_bloklari  — API mesajına eklenecek {"type": "text", ...} blokları
            kullanilan_referanslar — dahil edilen dosyaların göreceli yolları
    """
    if not ref_dosyalar:
        return [], []

    # Dosyaları kaynak tipine göre grupla, tekrarları temizle
    gruplari: dict[str, list[Path]] = {
        "confluence": [], "jira": [], "servisler": [], "diger": []
    }
    gorulmus: set[Path] = set()
    for f in ref_dosyalar:
        if f in gorulmus:
            continue
        gorulmus.add(f)
        try:
            rel = str(f.relative_to(REF_DIR)).replace("\\", "/")
        except ValueError:
            gruplari["diger"].append(f)
            continue
        if rel.startswith("confluence/"):
            gruplari["confluence"].append(f)
        elif rel.startswith("jira/"):
            gruplari["jira"].append(f)
        elif rel.startswith("services/"):
            gruplari["servisler"].append(f)
        else:
            gruplari["diger"].append(f)

    # (baslik, aciklama_icin_model, dosya_listesi, tip_toplam_limit, jira_modu)
    TIP_KONFIG = [
        (
            "CONFLUENCE DOKÜMANTASYONU",
            "Mevcut sistem dokümantasyonu, mimari kararlar, DB şeması, RBAC ve teknik detaylar. "
            "İlgili sayfalardaki bilgileri `[K: Confluence:<sayfa-adı>]` ile işaretle. "
            "Burada geçen tablo/kolon/servis adlarını teknik analizde aynen kullan.",
            gruplari["confluence"], MAX_CHARS_CONF_TOT, False,
        ),
        (
            "JİRA TASK GEÇMİŞİ",
            "Geçmiş geliştirme kararları, tamamlanan işler ve mevcut devam eden task'lar. "
            "İlgili task'ları `[K: Jira:KEY-123]` ile işaretle. "
            "Geçmiş kararlara atıfta bulun; çelişen karar varsa Açık Sorular'a taşı.",
            gruplari["jira"], MAX_CHARS_JIRA_TOT, True,
        ),
        (
            "API / SWAGGER TANIMLARI",
            "Mevcut servis endpoint'leri, HTTP metotları, request/response şemaları ve entegrasyon detayları. "
            "SADECE burada geçen endpoint'leri teknik analizde kullan — uydurma yasak. "
            "`[K: Swagger:<dosya>#/<path>]` ile işaretle.",
            gruplari["servisler"], MAX_CHARS_SERVIS_TOT, False,
        ),
        (
            "DİĞER REFERANSLAR",
            "Ek referans belgeler.",
            gruplari["diger"], MAX_CHARS_DIGER_TOT, False,
        ),
    ]

    bloklari: list[dict] = []
    kullanilan: list[str] = []

    for baslik, aciklama, dosya_listesi, tip_limit, jira_modu in TIP_KONFIG:
        if not dosya_listesi:
            continue

        metinler: list[str] = []
        toplam = 0

        for f in dosya_listesi:
            kalan = tip_limit - toplam
            if kalan <= 0:
                break
            try:
                rel = str(f.relative_to(REF_DIR)).replace("\\", "/")
            except ValueError:
                rel = f.name

            per_file = min(MAX_CHARS_REF, kalan)
            try:
                if jira_modu and f.suffix.lower() == ".json":
                    metin = _jira_json_to_md(f, per_file)
                else:
                    metin = dosya_oku(f, per_file)
            except Exception:
                continue

            if not metin.strip():
                continue

            metinler.append(f"#### {rel}\n{metin}")
            kullanilan.append(rel)
            toplam += len(metin)

        if metinler:
            bloklari.append({
                "type": "text",
                "text": (
                    f"### {baslik}\n{aciklama}\n\n"
                    + "\n\n---\n\n".join(metinler)
                ),
            })

    return bloklari, kullanilan


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


_RETRY_DENEMELER = 3
_RETRY_TABAN_GECIKME = 4  # saniye — 4, 8, 16


def _api_yeniden_dene(fn):
    """429 ve 5xx için exponential backoff retry decorator'ı."""
    import time as _t
    def _sarici(*a, **kw):
        son_hata = None
        for deneme in range(_RETRY_DENEMELER):
            try:
                return fn(*a, **kw)
            except anthropic.RateLimitError as e:
                son_hata = e
                bekleme = _RETRY_TABAN_GECIKME * (2 ** deneme)
                print(f"  ⚠ Rate limit (429). {bekleme}s sonra tekrar denenecek ({deneme+1}/{_RETRY_DENEMELER})")
                _t.sleep(bekleme)
            except anthropic.APIStatusError as e:
                status = getattr(e, "status_code", None)
                if status and 500 <= status < 600:
                    son_hata = e
                    bekleme = _RETRY_TABAN_GECIKME * (2 ** deneme)
                    print(f"  ⚠ Sunucu hatası ({status}). {bekleme}s sonra tekrar denenecek ({deneme+1}/{_RETRY_DENEMELER})")
                    _t.sleep(bekleme)
                else:
                    raise
            except anthropic.APIConnectionError as e:
                son_hata = e
                bekleme = _RETRY_TABAN_GECIKME * (2 ** deneme)
                print(f"  ⚠ Bağlantı hatası. {bekleme}s sonra tekrar denenecek ({deneme+1}/{_RETRY_DENEMELER})")
                _t.sleep(bekleme)
        raise son_hata if son_hata else RuntimeError("API çağrısı bilinmeyen sebepten başarısız.")
    return _sarici


@_api_yeniden_dene
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
