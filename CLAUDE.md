# brd-analyst-agent (Analyst Studio) — Claude Code Context

macOS masaüstü uygulaması. BRD/süreç dokümanı → RAG destekli analiz → Jira Epic/Story/Subtask.
Flask + Python **3.10+** (`str|None`), tarayıcı SPA `http://localhost:5002`.
İki akış: **Süreç → Teknik → Jira** (ana, FE/BE ayrımı) · **BRD → Kapsam**.

## Komutlar
- Kurulum: `bash setup.sh` · Başlat: `./start.sh` (veya Analyst Studio.app)
- Çalışma GUI üzerinden (subprocess `run.py`); ayrı terminal test komutu yok.
- **Backend kod değişince süreç yeniden başlatılmalı** (`use_reloader=False`; sekme kapatıp açmak/sayfa yenilemek Python sürecini yeniden başlatmaz — modüller `sys.modules`'ta cache'li). UI: Güncelleme sekmesi → **"Yeniden Başlat"** (`/api/restart`, koşulsuz). "Güncelle" (`/api/update`) yalnız `git pull` yeni commit çekerse restart eder → yerelde düzenlenen dosyalarda "zaten güncel" deyip restart ETMEZ. Restart mekanizması: `_yeniden_baslat_zamanla()` (app.py) — os.execv DEĞİL (execv dinlenen socket FD'sini devralır → "Address already in use"); mevcut süreç `os._exit` ile kapanır, ayrık yeni süreç ~1.5 sn gecikmeyle aynı komutla başlar.
- Test paketi yok. **Lint: `venv/bin/ruff check .`** — commit öncesi çalıştır, TEMİZ çıkmalı (F821 gibi gerçek bug'ları yakalar; legacy stil istisnaları `ruff.toml`'da). Ayrıca app'i başlatıp boot logunu kontrol et.

## AI modu (KRİTİK — her analiz çağrısını etkiler)
Pilot ekip **CLI modu**: `.env` `USE_CLAUDE_CLI=true` (Claude.ai aboneliği, per-token yok).
CLI **görsel BRD analiz EDEMEZ** (PDF/DOCX/TXT/MD olmalı). API modu (`ANTHROPIC_API_KEY`) ikincil.

## Klasör yapısı
- `app.py` Flask sunucu (~86 endpoint) · `run.py` orchestrator (subprocess) · `workflow.py` durum makinesi · `jira_agent.py` Jira OAuth+ADF
- `skills/` iş mantığı (`agent.py` = import bridge): `base.py` (sabitler/RAG/`_api_cagri`/19 prompt), `atlassian.py` (**CANONICAL** OAuth helper), `surec_analizi` `teknik_analiz` `delta_analizi` `brd_analizi` `kapsam_analizi` `jira_tasks` `jira_gorevleri` `backlog_senkron` (**UAT Mutabakat** ekranı — UAT board'u ↔ TRADE/OPS board karşılaştırma; **0-token deterministik**; eşleştirme = mevcut Jira issue-link (UAT linki hedef-projedeki bir key'e işaret ediyorsa o hedef taranan sette olmasa bile `_keyleri_cek` ile çekilip KESİN eşleşmeye dahil edilir — "kapsam dışı hedef") + **Story köprüsü** (UAT ve hedef task AYNI Story/Hikaye'ye bağlıysa dolaylı/transitif eşleşir — `_story_baglari`: Story tipli issue-link VEYA Story tipli **parent** (alt görev doğrudan Story altında); yalnız Story seviyesi, Epic hariç. parser artık `parent_key`/`parent_type` verir) + başlık/içerik Jaccard benzerliği; sonuç UAT sıra no'suna göre artan sıralı; Epic/Story (kapsayıcı) tipler ve UAT board'unda `UAT_HARIC_DURUMLAR` durumları (şu an "Created in Error"/"Create In Error") kapsam dışı; iptal durumları (İptal Edildi/CANCEL/CANCELED — `_iptal_statusu_mu`) ana akıştan ayrılıp ayrı **İptaller** kovasında (`iptaller`) toplanır — JQL `status NOT IN` + elde güvenlik ağı; UAT **ve Hedef** task'larının **atananı** (assignee) da çıktıda (`uat_atanan`/`hedef_atanan`/`atanan`) — her iki taraf için ekranda kolon + Durum/Atanan başlık filtreleri (istemci taraflı, AND); openpyxl ile sıfırdan çok sayfalı .xlsx rapor (`UAT_Mutabakat_*`, Atanan kolonlu). Excel girişi YOK. Not: modül adı `backlog_senkron`, endpoint'ler `/api/backlog/*`, iç sayfa id `backlog-senkron` — tarihsel) `confluence_yaz` `html_mockup` (canlı uygulama Chrome MCP ile gözlemlenip tasarım dili+component'ler baz alınarak, süreç analizindeki ekranlardan çalışan prototip) `sorular` `telemetri` (**Kullanım İzleme** — yalnız metadata; analiz olaylarını `logs/usage/events.jsonl`'e append eder + opsiyonel `USAGE_SINK_URL`'e fire-and-forget POST (Google Apps Script→Sheet write-only collector, bkz. `docs/telemetri-apps-script.md`); `istatistik()` 0-token deterministik özet. Emit noktaları: `run.py` (surec/teknik/brd/kapsam/jira_gonder; parent `_bekle` yalnız timeout'ta), app.py in-process endpoint'ler (mutabakat, gorev_analiz). Jira task adedi `telemetri.jira_task_arttir()` ile hem `jira_agent.jira_task_olustur` hem `jira_tasks._issue_olustur`'dan sayılır. Analist kimliği: session username > `ANALYST_NAME` env > OS user, subprocess'e `ANALIST` env ile geçer. **Owner-gate:** `USAGE_DASHBOARD=true` (AUTH'tan BAĞIMSIZ — analist build'lerinde yoktur → sekme gizli + `/api/usage/*` 403; `admin_gerekli` AUTH kapalıyken herkesi geçireceğinden ayrı bayrak ZORUNLU). "Kullanım" sekmesi yalnız owner'da; `/api/usage/stats|pull|export`, `auth/me` artık `usage_admin` döner. **Analist kimliği UI'dan:** Ayarlar → "Analist Adı Soyadı" → `analist.json` (gitignore, makineye özel; `/api/analist` GET/POST, owner-gate YOK); analist `.env`'e dokunmaz. Sink URL koda gömülü `VARSAYILAN_SINK_URL` (yalnız-yazma; `USAGE_SINK_URL` env override eder). Kimlik önceliği: login username > `ANALIST` env > `analist.json` > `ANALYST_NAME` env > OS user. Dashboard'da **isim sıralı sabit id** (`istatistik()` analistleri casefold ile sıralayıp 1..N id verir)). **Not:** `surec_analizi` çıktı formatı analiz ekibinin Confluence şablonudur (AMAÇ/MOCKUP/GEREKSİNİMLER→Ekranlar/ÖNERİLEN DB ALANLARI/GELİŞTİRME NOTLARI); ID'ler + `| Q-001 |` tablosu + `### Süreç Adımları` başlığı pipeline çapası olarak korunur (bkz. docs/MIMARI.md).
- `templates/index.html` SPA · `reference/` RAG kaynakları (Atlassian sync) · `output/ input/ history/ logs/` runtime · `backlog/` UAT Mutabakat üretilen .xlsx raporları (gitignore) · `docs/` detaylı referans
- **Bağımlılıklar** (`requirements.txt`): Flask, anthropic, requests, python-dotenv, PyMuPDF, Pillow, python-docx, ruff + **openpyxl** (UAT Mutabakat .xlsx rapor yazımı). `lxml` hâlâ kurulu (genel kullanım).
- `reference/live-app` Claude MCP/Chrome ekran+network gözlem çıktıları içindir (gitignore); bağlam filtresinde ana URL + 5 alt URL ve "Örnek ekran olarak kullan" seçeneği süreç/teknik analize canlı uygulama görevi olarak eklenir.
- **Canlı uygulama ÇALIŞMASI için `claude -p`'ye MCP + izin geçmek ZORUNLU** — bkz. `docs/MIMARI.md` "Canlı Uygulama (Chrome MCP)". `--allowedTools` verilmezse headless modda tarayıcı araçları sessizce reddedilir.

## Hard kurallar
1. **Türkçe** yaz (print/yorum/hata); teknik terimler İngilizce kalır.
2. Asla commit etme: `.env` (chmod 600) + makineye özel `reference/{context_filter,prompts,sources}.json` (gitignore'da; `*.json.example` izlenir, açılışta `_runtime_config_seed()` ile seed).
3. Atlassian helper → her zaman `skills/atlassian.py`'den import (duplicate tanım yok).
4. Yeni output dosyası → `IZIN_VERILEN_CIKTILAR` (app.py). Yeni Jira field → `jira_agent.py` + `skills/jira_tasks.py`.
5. Prompt önceliği: ekrandaki **Özel Prompt** (`context_filter.json → ozel_prompt`, analiz-bazlı, varsayılanın YERİNE geçer) > `reference/prompts.json` (kalıcı override) > `VARSAYILAN_PROMPTLAR` (base.py).
6. `sys.executable` kullan, Python yolu hard-code etme. `env_oku()` tırnakları strip eder.

## İlgili dosyalar — TÜM REPOYU TARAMA
Görev başında geniş dizinleri (`reference/`, `venv/`, `logs/`, `output/`) tarama. İhtiyaca göre:
- Mimari / sabitler / RAG / promptlar / workflow / 3-aşamalı teknik analiz / Jira Görevleri / cache / TL;DR → **`docs/MIMARI.md`**
- Tam endpoint kataloğu (~80) → **`docs/ENDPOINTS.md`**
- Auth / CSRF / güvenlik / dağıtım / onboarding → **`docs/GUVENLIK-DAGITIM.md`**
- Faz / değişiklik geçmişi → **`docs/DEGISIKLIK-GECMISI.md`**
- Belirli iş mantığı → ilgili tek `skills/<modül>.py` (önce o dosyayı oku, base.py'yi sadece gerekirse).

## CLAUDE.md / docs bakımı (zorunlu)
Dosya yapısı, skill sorumluluğu, endpoint, sabit/limit/model, prompt, workflow veya hard kural değişince
ilgili `docs/*` + bu özeti aynı/takip commit'inde güncelle. Sadece CSS/typo atlanabilir.
`.claude/hooks/post-commit-reminder.py` hatırlatır; nihai sorumluluk Claude'da.
