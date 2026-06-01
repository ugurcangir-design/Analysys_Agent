"""
Confluence Yazma Skill — Adım 6.
output/ dosyasını Confluence'a sayfa olarak yayımlar.
Markdown → Confluence storage format dönüşümü burada yapılır.
"""

import re
from .base import OUTPUT_DIR, dosya_oku, MAX_CHARS_GENEL
from .atlassian import (
    confluence_sayfa_bul,
    confluence_sayfa_olustur,
    confluence_sayfa_guncelle,
)


# ─── Markdown → Confluence Storage Format ────────────────────────────────────

def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _inline(text: str) -> str:
    """Markdown inline syntax → Confluence storage HTML inline elementler."""
    # Inline code parçalarını önce koru
    segments = re.split(r"(`[^`\n]+`)", text)
    result = []
    for seg in segments:
        if seg.startswith("`") and seg.endswith("`") and len(seg) > 2:
            result.append(f"<code>{_escape(seg[1:-1])}</code>")
            continue
        seg = _escape(seg)
        seg = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", seg)
        seg = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", seg)
        seg = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", seg)
        seg = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<em>\1</em>", seg)
        seg = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', seg)
        result.append(seg)
    return "".join(result)


def _table(lines: list[str]) -> str:
    """Markdown tablo satırları → Confluence storage HTML tablosu."""
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return ""

    # İkinci satır ayırıcı mı?
    is_header = (
        len(rows) >= 2
        and all(re.match(r"^[-:\s]+$", c) for c in rows[1] if c)
    )
    header_row = rows[0] if is_header else None
    data_rows = rows[2:] if is_header else rows

    html = ["<table><tbody>"]
    if header_row:
        cells = "".join(f"<th><strong>{_inline(c)}</strong></th>" for c in header_row)
        html.append(f"<tr>{cells}</tr>")
    for row in data_rows:
        if all(re.match(r"^[-:\s]+$", c) for c in row if c):
            continue
        cells = "".join(f"<td>{_inline(c)}</td>" for c in row)
        html.append(f"<tr>{cells}</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)


def md_to_storage(md: str) -> str:
    """Markdown → Confluence storage format (HTML subset + AC macros)."""
    lines = md.splitlines()
    out = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith("```"):
            lang = stripped[3:].strip() or "none"
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # kapanış ```
            code = "\n".join(code_lines).replace("]]>", "]]&gt;")
            out.append(
                f'<ac:structured-macro ac:name="code" ac:schema-version="1">'
                f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
                f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
                f"</ac:structured-macro>"
            )
            continue

        # Heading
        if stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            text = _inline(stripped[level:].strip())
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Yatay çizgi
        if re.match(r"^[-*_]{3,}\s*$", stripped) and stripped:
            out.append("<hr/>")
            i += 1
            continue

        # Tablo
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(_table(table_lines))
            continue

        # Sırasız liste
        if re.match(r"^[-*+]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*+]\s+", lines[i].strip()):
                item_text = re.sub(r"^[-*+]\s+", "", lines[i].strip())
                items.append(f"<li><p>{_inline(item_text)}</p></li>")
                i += 1
            out.append(f'<ul>{"".join(items)}</ul>')
            continue

        # Sıralı liste
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(f"<li><p>{_inline(item_text)}</p></li>")
                i += 1
            out.append(f'<ol>{"".join(items)}</ol>')
            continue

        # Boş satır
        if not stripped:
            i += 1
            continue

        # Paragraf — blok eleman olmayana kadar satırları birleştir
        para = []
        while i < len(lines):
            ln = lines[i].strip()
            if not ln:
                break
            if (ln.startswith("#") or ln.startswith("```") or ln.startswith("|")
                    or re.match(r"^[-*+]\s+", ln) or re.match(r"^\d+\.\s+", ln)
                    or re.match(r"^[-*_]{3,}\s*$", ln)):
                break
            para.append(ln)
            i += 1
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")

    return "\n".join(out)


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

# output dosya adı → varsayılan Confluence sayfa başlığı
_BASLIKLAR = {
    "surec-analizi.md":       "Süreç Analizi",
    "teknik-analiz.md":       "Teknik Analiz",
    "acik-sorular.md":        "Açık Sorular",
    "brd-analizi.md":         "BRD Analizi",
    "brd-sorular.md":         "BRD Soruları",
    "kapsam-analizi.md":      "Kapsam Analizi",
    "alternatif-surecler.md": "Alternatif Süreçler",
    "api-schema.yaml":        "API Şema",
    "db-schema.sql":          "Veritabanı Şeması",
}


def confluence_yayimla(
    dosya_adi: str,
    space_key: str,
    cloud_id: str,
    title: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """
    output/{dosya_adi} dosyasını Confluence'a yayımlar.
    Sayfa varsa günceller, yoksa oluşturur.
    Döndürür: {"page_id": ..., "url": ..., "title": ..., "action": "olusturuldu"|"guncellendi"}
    """
    yol = OUTPUT_DIR / dosya_adi
    if not yol.exists():
        raise FileNotFoundError(f"output/{dosya_adi} bulunamadı.")

    # İçerik oku
    icerik = dosya_oku(yol, MAX_CHARS_GENEL)

    # Başlık belirle
    if not title:
        title = _BASLIKLAR.get(dosya_adi, yol.stem.replace("-", " ").title())

    # Confluence storage formatına dönüştür
    if yol.suffix == ".md":
        storage = md_to_storage(icerik)
    else:
        # SQL, YAML vb. → code macro
        ext = yol.suffix.lstrip(".")
        escaped = icerik.replace("]]>", "]]&gt;")
        storage = (
            f'<ac:structured-macro ac:name="code" ac:schema-version="1">'
            f'<ac:parameter ac:name="language">{ext}</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{escaped}]]></ac:plain-text-body>"
            f"</ac:structured-macro>"
        )

    # Mevcut sayfayı ara
    mevcut = confluence_sayfa_bul(title, space_key, cloud_id)

    if mevcut:
        result = confluence_sayfa_guncelle(
            page_id=mevcut["id"],
            title=title,
            storage_body=storage,
            current_version=mevcut["version"],
            cloud_id=cloud_id,
        )
        action = "guncellendi"
        print(f"✓ Confluence güncellendi: {title} (id={result['id']})")
    else:
        result = confluence_sayfa_olustur(
            title=title,
            storage_body=storage,
            space_key=space_key,
            cloud_id=cloud_id,
            parent_id=parent_id,
        )
        action = "olusturuldu"
        print(f"✓ Confluence sayfası oluşturuldu: {title} (id={result['id']})")

    return {
        "page_id": result["id"],
        "url": result["url"],
        "title": title,
        "action": action,
    }
