# brd-analyst-agent (Analyst Studio) — Claude Code Context

macOS masaüstü uygulaması. BRD/süreç dokümanı → RAG destekli analiz → Jira Epic/Story/Subtask.
Flask + Python **3.10+** (`str|None`), tarayıcı SPA `http://localhost:5002`.
İki akış: **Süreç → Teknik → Jira** (ana, FE/BE ayrımı) · **BRD → Kapsam**.

## Komutlar
- Kurulum: `bash setup.sh` · Başlat: `./start.sh` (veya Analyst Studio.app)
- Çalışma GUI üzerinden (subprocess `run.py`); ayrı terminal test komutu yok.
- Lint/test paketi yok — değişiklik sonrası `python -c "import ast; ast.parse(open('<dosya>').read())"` ile sözdizimi doğrula, app'i başlatıp boot logunu kontrol et.

## AI modu (KRİTİK — her analiz çağrısını etkiler)
Pilot ekip **CLI modu**: `.env` `USE_CLAUDE_CLI=true` (Claude.ai aboneliği, per-token yok).
CLI **görsel BRD analiz EDEMEZ** (PDF/DOCX/TXT/MD olmalı). API modu (`ANTHROPIC_API_KEY`) ikincil.

## Klasör yapısı
- `app.py` Flask sunucu (~80 endpoint) · `run.py` orchestrator (subprocess) · `workflow.py` durum makinesi · `jira_agent.py` Jira OAuth+ADF
- `skills/` iş mantığı (`agent.py` = import bridge): `base.py` (sabitler/RAG/`_api_cagri`/16 prompt), `atlassian.py` (**CANONICAL** OAuth helper), `surec_analizi` `teknik_analiz` `brd_analizi` `kapsam_analizi` `jira_tasks` `jira_gorevleri` `confluence_yaz` `html_mockup` `sorular`
- `templates/index.html` SPA · `reference/` RAG kaynakları (Atlassian sync) · `output/ input/ history/ logs/` runtime · `docs/` detaylı referans
- `reference/live-app` Claude MCP/Chrome ekran+network gözlem çıktıları içindir (gitignore); bağlam filtresinde ana URL + 5 alt URL ve "Örnek ekran olarak kullan" seçeneği süreç/teknik analize canlı uygulama görevi olarak eklenir.
- **Canlı uygulama ÇALIŞMASI için `claude -p`'ye MCP + izin geçmek ZORUNLU** — bkz. `docs/MIMARI.md` "Canlı Uygulama (Chrome MCP)". `--allowedTools` verilmezse headless modda tarayıcı araçları sessizce reddedilir.

## Hard kurallar
1. **Türkçe** yaz (print/yorum/hata); teknik terimler İngilizce kalır.
2. Asla commit etme: `.env` (chmod 600) + makineye özel `reference/{context_filter,prompts,sources}.json` (gitignore'da; `*.json.example` izlenir, açılışta `_runtime_config_seed()` ile seed).
3. Atlassian helper → her zaman `skills/atlassian.py`'den import (duplicate tanım yok).
4. Yeni output dosyası → `IZIN_VERILEN_CIKTILAR` (app.py). Yeni Jira field → `jira_agent.py` + `skills/jira_tasks.py`.
5. Prompt değişikliği → `VARSAYILAN_PROMPTLAR` (base.py) veya `reference/prompts.json` (override öncelikli).
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
