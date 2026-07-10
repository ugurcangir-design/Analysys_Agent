#!/usr/bin/env python3
"""
PostToolUse hook (Bash matcher).
Bash ile yapılan `git commit` çağrısından sonra Claude'a CLAUDE.md'yi
gözden geçirmesini hatırlatır. Sadece commit komutlarında ek bağlam üretir.
"""
import sys
import json


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    response = data.get("tool_response") or {}

    # Sadece git commit komutlarında çalış; rebase/log/diff vb. atla
    if "git commit" not in cmd:
        return
    # Başarısız commit ise atla
    if isinstance(response, dict):
        if response.get("exit_code") not in (None, 0):
            return

    mesaj = (
        "⚠ Commit yapıldı — CLAUDE.md güncel mi? Şu konulardan biri "
        "etkilendiyse CLAUDE.md'yi güncelle ve aynı veya takip eden "
        "commit'te onu da push et:\n"
        "  • Dosya yapısı / yeni veya kaldırılan modül\n"
        "  • Skill modüllerinin sorumlulukları\n"
        "  • Endpoint'ler (yeni / kaldırılan / yol değişikliği)\n"
        "  • Sabitler / limitler / model adı / heartbeat değerleri\n"
        "  • Sistem promptları / EK KURALLAR / ID şeması\n"
        "  • FE/BE katman akışı veya workflow durumları\n"
        "  • Geliştirme kuralları / bilinen kısıtlamalar\n"
        "Sadece görsel/CSS/typo değişikliyse atla."
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": mesaj,
        }
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
