"""
Jira Task Hiyerarşisi Skill — Adım 7.
teknik-analiz.md → Epic + Story + Subtask yapısı → Jira'ya yükle.
"""

import json
import sys
import re
from pathlib import Path

from .base import (
    _api_cagri, _xml_ayir, _metin_sikistir,
    dosya_oku, OUTPUT_DIR,
    MAX_CHARS_GENEL,
)
from .atlassian import env_oku, atlassian_get, atlassian_post

# markdown_to_adf + yardımcıları jira_agent.py'den al
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from jira_agent import _p, _h, _bullet  # noqa: E402


# ─── Token Limiti ─────────────────────────────────────────────────────────────

MAX_TOKENS_HIERARCHY = 4_000


# ─── ADF Yardımcıları ─────────────────────────────────────────────────────────

def _adf_doc(content: list) -> dict:
    return {"type": "doc", "version": 1, "content": content}


def _hikaye_adf(description: str, acceptance_criteria: list[str]) -> dict:
    """Story açıklama + acceptance criteria → ADF doc."""
    content = []
    for line in description.strip().splitlines():
        line = line.strip()
        if line:
            content.append(_p(line))
    if acceptance_criteria:
        content.append(_h("Acceptance Criteria", 3))
        content.append(_bullet([c.strip() for c in acceptance_criteria if c.strip()]))
    if not content:
        content = [_p(description or "(açıklama yok)")]
    return _adf_doc(content)


def _gorev_adf(description: str) -> dict:
    """Subtask açıklaması → ADF doc."""
    content = [_p(line.strip()) for line in description.strip().splitlines() if line.strip()]
    return _adf_doc(content or [_p(description or "(açıklama yok)")])


# ─── Proje Tip Tespiti ────────────────────────────────────────────────────────

def _proje_bilgi(project_key: str, cloud_id: str) -> dict:
    """
    Proje issue type'larını ve stilini döndürür.
    Returns: {
        "issue_types": {"epic": "id", "story": "id", "subtask": "id", "task": "id"},
        "has_epic": bool,
        "has_story": bool,
        "subtask_name": str,
    }
    """
    data = atlassian_get(f"/rest/api/3/project/{project_key}", cloud_id=cloud_id)
    types = {it["name"].lower(): it["id"] for it in data.get("issueTypes", [])}

    # Subtask ismi projeden projeye değişir
    subtask_name = next(
        (n for n in types if n in ("subtask", "sub-task", "alt görev")),
        None,
    )

    return {
        "issue_types": types,
        "has_epic":  "epic"  in types,
        "has_story": "story" in types,
        "subtask_id": types.get(subtask_name) if subtask_name else None,
        "subtask_name": subtask_name,
        "epic_id":  types.get("epic"),
        "story_id": types.get("story"),
        "task_id":  types.get("task"),
    }


# ─── Issue Oluşturma ──────────────────────────────────────────────────────────

def _issue_olustur(
    summary: str,
    description_adf: dict,
    issue_type_id: str,
    project_key: str,
    cloud_id: str,
    parent_key: str | None = None,
) -> str:
    """Tek issue oluştur, key döndür."""
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary[:255],
        "issuetype": {"id": issue_type_id},
        "description": description_adf,
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}

    data = atlassian_post("/rest/api/3/issue", body={"fields": fields}, cloud_id=cloud_id)
    return data["key"]


# ─── AI Prompt ────────────────────────────────────────────────────────────────

_HIERARCHY_SISTEM = """Kıdemli yazılım mimarısın. Teknik analiz dokümanından Jira task hiyerarşisi üret.

Kurallar:
- 1 Epic: tüm projeyi kapsayan üst başlık
- 3-7 Story: her biri bağımsız bir fonksiyonel alan (BE, FE, entegrasyon, vb.)
- Her Story için 2-4 Subtask: somut, ölçülebilir geliştirme adımları
- Her Story için 2-5 acceptance_criteria: test edilebilir kabul kriteri
- Tüm metinler Türkçe; teknik terimler (API, endpoint, vb.) İngilizce kalabilir

Yanıtı SADECE aşağıdaki XML+JSON formatında ver:

<jira_hierarchy>
{
  "epic_summary": "...",
  "epic_description": "...",
  "stories": [
    {
      "summary": "...",
      "description": "...",
      "acceptance_criteria": ["...", "..."],
      "subtasks": [
        {"summary": "...", "description": "..."}
      ]
    }
  ]
}
</jira_hierarchy>"""


def _hierarchy_uret(teknik_analiz: str) -> dict:
    """teknik-analiz.md içeriğinden Jira hiyerarşi JSON'ı üret."""
    from .base import prompt_yukle
    mesajlar = [{"role": "user", "content": [
        {"type": "text", "text": f"### Teknik Analiz\n\n{teknik_analiz}\n\nJira task hiyerarşisini üret."}
    ]}]
    yanit = _api_cagri(prompt_yukle("jira_tasks"), mesajlar, max_tokens=MAX_TOKENS_HIERARCHY)
    yanit = _metin_sikistir(yanit)
    json_str = _xml_ayir(yanit, "jira_hierarchy")

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # JSON başını/sonunu temizleyip tekrar dene
        cleaned = re.sub(r'^```[a-z]*\n?', '', json_str.strip()).rstrip('`').strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(f"AI yanıtı JSON parse edilemedi: {e}\n---\n{json_str[:500]}")


# ─── Issue Type ID Belirleme ──────────────────────────────────────────────────

def _issue_type_idleri(proje: dict, project_key: str) -> tuple[str, str, str]:
    """Proje bilgisinden (epic, story, subtask) issue type id'lerini belirler.

    Epic+Story tipleri varsa onları, yoksa Task+Subtask fallback'i kullanır.
    """
    if proje["has_epic"] and proje["has_story"]:
        epic_type_id  = proje["epic_id"]
        story_type_id = proje["story_id"]
        sub_type_id   = proje["subtask_id"] or proje["task_id"]
    else:
        epic_type_id  = proje["task_id"]
        story_type_id = proje["task_id"]
        sub_type_id   = proje["subtask_id"] or proje["task_id"]

    if not epic_type_id or not story_type_id:
        raise ValueError(
            f"Proje '{project_key}' için uygun issue type bulunamadı. "
            f"Mevcut tipler: {list(proje['issue_types'].keys())}"
        )
    return epic_type_id, story_type_id, sub_type_id


# ─── Önizleme: AI Hiyerarşisi Üret (Jira'ya yazmaz) ──────────────────────────

def jira_hiyerarsi_uret(teknik_analiz_dosya: str = "teknik-analiz.md") -> dict:
    """teknik-analiz.md → AI task hiyerarşisi önerir. Jira'ya HİÇBİR ŞEY YAZMAZ.

    Analistin ekrandan seçim yapabilmesi için önizleme verisi döndürür:
    {
        "hierarchy": {epic_summary, epic_description, stories: [...]},
        "proje": {key, has_epic, has_story, subtask_name},
        "ozet": {epic: 1, story: N, subtask: M}
    }
    """
    env = env_oku()
    cloud_id    = env.get("JIRA_CLOUD_ID", "")
    project_key = env.get("JIRA_PROJECT_KEY", "")
    if not cloud_id or not project_key:
        raise EnvironmentError("JIRA_CLOUD_ID veya JIRA_PROJECT_KEY tanımlı değil.")

    # 1. Teknik analizi oku
    dosya_yolu = OUTPUT_DIR / teknik_analiz_dosya
    if not dosya_yolu.exists():
        raise FileNotFoundError(f"{teknik_analiz_dosya} bulunamadı. Önce teknik analiz yapın.")
    teknik_analiz = dosya_oku(dosya_yolu, MAX_CHARS_GENEL)
    # Yönetici Özeti (TL;DR) Jira'ya gitmemeli — hiyerarşi üretimine girdi olmadan çıkar.
    from .base import yonetici_ozetini_cikar
    teknik_analiz = yonetici_ozetini_cikar(teknik_analiz)
    print(f"  Teknik analiz okundu ({len(teknik_analiz):,} karakter)")

    # 2. Proje issue type'larını öğren (oluşturma değil, sadece tip tespiti)
    print("  Proje issue type'ları alınıyor...")
    proje = _proje_bilgi(project_key, cloud_id)
    print(f"  Epic: {'var' if proje['has_epic'] else 'yok'} | "
          f"Story: {'var' if proje['has_story'] else 'yok'} | "
          f"Subtask: {proje.get('subtask_name', 'yok')}")
    # İssue type'ların geçerli olduğunu önizleme aşamasında doğrula
    _issue_type_idleri(proje, project_key)

    # 3. AI'dan hiyerarşi üret
    print("  AI'dan task hiyerarşisi üretiliyor...")
    hierarchy = _hierarchy_uret(teknik_analiz)

    stories = hierarchy.get("stories", []) or []
    return {
        "hierarchy": hierarchy,
        "proje": {
            "key": project_key,
            "has_epic": proje["has_epic"],
            "has_story": proje["has_story"],
            "subtask_name": proje.get("subtask_name"),
        },
        "ozet": {
            "epic": 1,
            "story": len(stories),
            "subtask": sum(len(s.get("subtasks", []) or []) for s in stories),
        },
    }


# ─── Oluşturma: Seçilen Hiyerarşiyi Jira'da Aç ───────────────────────────────

def jira_hiyerarsi_olustur(hierarchy: dict, confluence_url: str | None = None) -> dict:
    """Analist tarafından seçilmiş/düzenlenmiş hiyerarşiyi Jira'da oluşturur.

    hierarchy yalnızca analistin seçtiği öğeleri içermelidir:
    {
        "epic_dahil": bool,                # Epic oluşturulsun mu
        "epic_summary": str,
        "epic_description": str,
        "stories": [                        # SADECE seçilen story'ler
            {summary, description, acceptance_criteria, subtasks: [...]}  # SADECE seçilen subtask'lar
        ]
    }

    Döndürür:
    {"epic_key": str|None, "stories": [...], "toplam": int, "proje": str}
    """
    env = env_oku()
    cloud_id    = env.get("JIRA_CLOUD_ID", "")
    project_key = env.get("JIRA_PROJECT_KEY", "")
    if not cloud_id or not project_key:
        raise EnvironmentError("JIRA_CLOUD_ID veya JIRA_PROJECT_KEY tanımlı değil.")

    epic_dahil   = bool(hierarchy.get("epic_dahil", True))
    stories_data = hierarchy.get("stories", []) or []

    if not epic_dahil and not stories_data:
        raise ValueError("Oluşturulacak öğe seçilmedi. En az bir öğe seçin.")

    epic_summary = (hierarchy.get("epic_summary") or "").strip()
    if epic_dahil and not epic_summary:
        raise ValueError("Epic başlığı boş olamaz.")

    # Proje tipini öğren ve issue type id'lerini belirle
    print("  Proje issue type'ları alınıyor...")
    proje = _proje_bilgi(project_key, cloud_id)
    epic_type_id, story_type_id, sub_type_id = _issue_type_idleri(proje, project_key)

    sub_toplam = sum(len(s.get("subtasks", []) or []) for s in stories_data)
    toplam = (1 if epic_dahil else 0) + len(stories_data) + sub_toplam
    print(f"  Plan: {1 if epic_dahil else 0} Epic + {len(stories_data)} Story + "
          f"{sub_toplam} Subtask = {toplam} issue")

    # 1. Epic (seçildiyse)
    epic_key: str | None = None
    if epic_dahil:
        epic_desc_lines = []
        if hierarchy.get("epic_description"):
            epic_desc_lines.append(_p(hierarchy["epic_description"]))
        if confluence_url:
            epic_desc_lines.append(_p(f"Analiz dokümanı: {confluence_url}"))
        epic_adf = _adf_doc(epic_desc_lines or [_p("Proje ana görevi")])

        print(f"  Epic oluşturuluyor: {epic_summary[:60]}...")
        epic_key = _issue_olustur(
            summary=epic_summary,
            description_adf=epic_adf,
            issue_type_id=epic_type_id,
            project_key=project_key,
            cloud_id=cloud_id,
        )
        print(f"  ✓ Epic: {epic_key}")

    # 2. Story + Subtask'lar
    sonuclar = []
    for i, story in enumerate(stories_data, 1):
        story_summary = (story.get("summary") or f"Story {i}").strip()
        story_desc    = story.get("description", "")
        story_ac      = story.get("acceptance_criteria", []) or []
        story_adf     = _hikaye_adf(story_desc, story_ac)

        print(f"  Story {i}/{len(stories_data)}: {story_summary[:60]}...")
        story_key = _issue_olustur(
            summary=story_summary,
            description_adf=story_adf,
            issue_type_id=story_type_id,
            project_key=project_key,
            cloud_id=cloud_id,
            parent_key=epic_key,   # None ise standalone oluşturulur
        )
        print(f"    ✓ {story_key}")

        subtask_keys = []
        for sub in story.get("subtasks", []) or []:
            sub_summary = (sub.get("summary") or "Subtask").strip()
            sub_adf     = _gorev_adf(sub.get("description", ""))
            sub_key = _issue_olustur(
                summary=sub_summary,
                description_adf=sub_adf,
                issue_type_id=sub_type_id or story_type_id,
                project_key=project_key,
                cloud_id=cloud_id,
                parent_key=story_key,
            )
            subtask_keys.append(sub_key)
            print(f"      ✓ {sub_key}: {sub_summary[:50]}")

        sonuclar.append({
            "key": story_key,
            "summary": story_summary,
            "subtasks": subtask_keys,
        })

    print(f"✓ Toplam {toplam} issue oluşturuldu." + (f" Epic: {epic_key}" if epic_key else ""))
    return {
        "epic_key": epic_key,
        "stories": sonuclar,
        "toplam": toplam,
        "proje": project_key,
    }


# ─── Geriye Dönük Uyumluluk ───────────────────────────────────────────────────

def jira_tasks_olustur(
    teknik_analiz_dosya: str = "teknik-analiz.md",
    confluence_url: str | None = None,
) -> dict:
    """Eski tek-adımlı API: önizleme üretir + tüm öğeleri seçimsiz oluşturur."""
    onizleme = jira_hiyerarsi_uret(teknik_analiz_dosya)
    hierarchy = onizleme["hierarchy"]
    hierarchy["epic_dahil"] = True
    return jira_hiyerarsi_olustur(hierarchy, confluence_url=confluence_url)
