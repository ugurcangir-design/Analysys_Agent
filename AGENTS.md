# brd-analyst-agent (Analyst Studio) — Agent Context

> **Tek kaynak-doğrusu: [`CLAUDE.md`](CLAUDE.md).**
> Bu dosya içerik KOPYALAMAZ — kopya doküman kaçınılmaz bayatlar. (Önceki sürümü
> "Codex.ai aboneliği" ve var olmayan bir `UI_CODE_REFERENCE` toggle'ı iddia ediyordu;
> ikisi de yanlıştı.) Codex ve diğer agent araçları aşağıdaki dosyaları okumalı.

| Ne arıyorsan | Nereye bak |
|---|---|
| Proje özeti, komutlar, **AI modu (CLI/API)**, klasör yapısı, hard kurallar | **`CLAUDE.md`** |
| Mimari, sabitler, RAG, promptlar, 3-aşamalı teknik analiz, **canlı uygulama (Chrome MCP)**, cache/TL;DR | `docs/MIMARI.md` |
| Tam endpoint kataloğu (~80) | `docs/ENDPOINTS.md` |
| Auth / CSRF / güvenlik / dağıtım | `docs/GUVENLIK-DAGITIM.md` |
| Faz / değişiklik geçmişi | `docs/DEGISIKLIK-GECMISI.md` |

## Kritik hatırlatmalar (tam liste CLAUDE.md'de)
- Analizler **Claude Code CLI** ile çalışır (`.env` `USE_CLAUDE_CLI=true` → **Claude.ai** aboneliği).
- Kod, yorum, hata mesajları **Türkçe**; teknik terimler İngilizce.
- `.env` ve `reference/{context_filter,prompts,sources}.json` **asla commit edilmez**.
- Değişiklik sonrası: `venv/bin/ruff check <dosya>` + uygulamayı başlatıp boot logunu kontrol et.
- Geniş dizinleri (`reference/`, `venv/`, `logs/`, `output/`) tarama — bkz. `.claudeignore`.

## Bakım
Dosya yapısı, skill sorumluluğu, endpoint, sabit/limit/model, prompt, workflow veya hard kural
değişince ilgili `docs/*` + `CLAUDE.md` güncellenir. Bu dosya yalnızca yönlendirme içerir;
kural/mimari eklemeyin. `.codex/hooks/post-commit-reminder.py` hatırlatır.
