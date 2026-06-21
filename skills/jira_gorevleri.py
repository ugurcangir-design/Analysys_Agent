"""Jira Görevleri Skill — Epic/Story altındaki bir-seviye-alt görevleri çek,
'hazır / detay gerekir' olarak sınıflandır (yapısal + AI), ve iki manuel aksiyon:

  Özellik 1 — gorev_standart_formatla(): mevcut görevi agent'ın standart görev
              formatına (Amaç / Değişiklikler / Referans / Kabul Kriteri) çevirir.
  Özellik 2 — gorev_analiz_et(): teknik analiz motoruyla görevi detaylandırır.

Her iki çıktı da analist onayından sonra gorev_jiraya_yaz() ile Jira görevinin
description'ına (markdown→ADF) yazılır. Okuma/yazma canonical skills/atlassian.py
üzerinden; format jira_agent.markdown_to_adf ile (teknik analiz task'ı formatı).
"""

import json
import re
import sys
from pathlib import Path

from .atlassian import env_oku, atlassian_post, atlassian_put
from .base import (
    _api_cagri, _xml_ayir, _metin_sikistir,
    prompt_yukle, extended_thinking_acik,
    referans_dosyalari_hazirla, _ref_bloklari_olustur,
    MAX_TOKENS_KISA, MAX_TOKENS_COMBINED,
)

# markdown_to_adf — jira_agent.py'den (teknik analiz task'ı açarkenki format)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from jira_agent import markdown_to_adf  # noqa: E402


# ─── Standart Görev Şablonu (Özellik 1 hedef formatı) ────────────────────────

STANDART_GOREV_SABLONU = """## Amaç
[1-2 cümle: ne geliştirilecek ve neden — iş gerekçesi]

## Değişiklikler
- [somut, madde madde değişiklikler]

## Referans / Yaklaşım
- [etkilenen ekran/dosyalar (örn. src/...), teknik yaklaşım, backend/i18n notu]

## Kabul Kriteri
- [test edilebilir, gözlemlenebilir kriterler]"""


# ─── Cloud ID ────────────────────────────────────────────────────────────────

def _cloud_id() -> str:
    cid = env_oku().get("JIRA_CLOUD_ID", "")
    if not cid:
        raise RuntimeError("Jira bağlı değil (JIRA_CLOUD_ID yok). Ayarlar'dan Jira'ya bağlanın.")
    return cid


# ─── ADF Okuma (description → düz metin) ─────────────────────────────────────

def _adf_to_text(node) -> str:
    """ADF description'ı okunabilir düz metne çevirir (kart görünümü +
    sınıflandırma/analiz girdisi). Başlıkları boş satırla ayırır, madde
    işaretlerini korur — yapıyı düzgün ayrıştırır."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    tip = node.get("type")
    if tip == "text":
        return node.get("text", "")
    if tip == "hardBreak":
        return "\n"
    icerik = "".join(_adf_to_text(c) for c in node.get("content", []) or [])
    if tip == "heading":
        return "\n" + icerik.strip() + "\n"        # başlık öncesi boş satır
    if tip == "paragraph":
        return icerik + "\n"
    if tip == "listItem":
        return "• " + icerik.strip() + "\n"
    if tip in ("bulletList", "orderedList", "tableRow"):
        return icerik + "\n"
    return icerik


# ─── Alt Görevleri Çek (bir seviye alt) ──────────────────────────────────────

_ID_DESENI = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def alt_gorevleri_cek(parent_key: str) -> list[dict]:
    """Verilen Epic/Story KEY'inin BİR SEVİYE altındaki görevleri çeker.
    Önce `parent = KEY` (team-managed + sub-task), boş dönerse epic için
    `"Epic Link" = KEY` (company-managed) fallback'i denenir."""
    parent_key = (parent_key or "").strip().upper()
    if not _ID_DESENI.match(parent_key):
        raise ValueError(f"Geçersiz Jira anahtarı: '{parent_key}' (örn. PROJ-123 olmalı)")

    cloud_id = _cloud_id()
    alanlar = ["summary", "description", "status", "issuetype", "priority", "assignee", "parent"]

    def _ara(jql: str) -> list[dict]:
        gorevler, next_token = [], None
        while True:
            body = {"jql": jql, "fields": alanlar, "maxResults": 100}
            if next_token:
                body["nextPageToken"] = next_token
            data = atlassian_post("/rest/api/3/search/jql", body=body, cloud_id=cloud_id)
            for issue in data.get("issues", []):
                f = issue.get("fields", {})
                desc = f.get("description")
                desc_metin = _adf_to_text(desc) if isinstance(desc, dict) else (desc or "")
                gorevler.append({
                    "key": issue["key"],
                    "summary": f.get("summary", ""),
                    "status": (f.get("status") or {}).get("name", ""),
                    "type": (f.get("issuetype") or {}).get("name", ""),
                    "priority": (f.get("priority") or {}).get("name", ""),
                    "assignee": (f.get("assignee") or {}).get("displayName", ""),
                    "description": desc_metin.strip(),
                })
            next_token = data.get("nextPageToken")
            if not next_token:
                break
        return gorevler

    # "Alt görev" tanımı projeden projeye değişir. Üç modeli de kapsa, birleştir:
    #   1. parent = KEY           → gerçek sub-task / team-managed çocuk
    #   2. "Epic Link" = KEY      → company-managed epic çocuğu
    #   3. linkedIssues(KEY)      → issue-link (Relates vb.) ile bağlı görevler
    #                               (bazı ekipler hiyerarşi yerine bunu kullanır)
    jql_adaylari = [
        f"parent = {parent_key}",
        f'"Epic Link" = {parent_key}',
        f'issue in linkedIssues("{parent_key}")',
    ]
    birlesik: dict[str, dict] = {}
    for jql in jql_adaylari:
        try:
            for g in _ara(f"{jql} ORDER BY created ASC"):
                if g["key"] != parent_key:
                    birlesik.setdefault(g["key"], g)  # ilk gelen kazanır, tekrarı önle
        except Exception:
            continue  # alan/JQL projede yoksa sessizce geç
    return list(birlesik.values())


# ─── Sınıflandırma: Yapısal + AI ─────────────────────────────────────────────

_BOLUM_DESENLERI = {
    "amac": re.compile(r"(?im)^\s*#{0,4}\s*ama[cç]\b|amaç\s*:"),
    "degisiklik": re.compile(r"(?im)^\s*#{0,4}\s*de[gğ]i[sş]iklik|değişiklik"),
    "referans": re.compile(r"(?im)^\s*#{0,4}\s*(referans|yakla[sş][iı]m)\b"),
    "kabul": re.compile(r"(?im)^\s*#{0,4}\s*kabul\s*kriter|acceptance"),
}
_DOSYA_DESENI = re.compile(r"\b[\w./-]+\.(?:tsx|ts|jsx|js|py|java|cs|vue|json|ya?ml|sql|md)\b")


def _yapisal_skor(gorev: dict) -> dict:
    """Görev içeriğinin standart bölümleri taşıyıp taşımadığını deterministik ölçer."""
    metin = f"{gorev.get('summary','')}\n{gorev.get('description','')}"
    bolumler = {ad: bool(d.search(metin)) for ad, d in _BOLUM_DESENLERI.items()}
    dosya_ref = bool(_DOSYA_DESENI.search(metin))
    uzun = len(gorev.get("description", "")) >= 120
    bolum_sayisi = sum(bolumler.values())
    # Yapısal "hazır" sinyali: kabul kriteri + (amaç/değişiklik) + (dosya ya da uzunluk)
    hazir_yapisal = bolumler["kabul"] and (bolumler["amac"] or bolumler["degisiklik"]) and (dosya_ref or uzun)
    return {
        "bolumler": bolumler,
        "bolum_sayisi": bolum_sayisi,
        "dosya_ref": dosya_ref,
        "uzun": uzun,
        "hazir_yapisal": hazir_yapisal,
    }


def _siniflandirma_prompt() -> str:
    return (
        "Kıdemli teknik analistsin. Sana bir Jira üst görevinin altındaki alt görevler "
        "verilecek. Her görevin BAŞLIK ve AÇIKLAMASINI OKU; içeriğine göre sınıflandır.\n\n"
        "'hazir' = amaç net, yapılacak değişiklik somut, etkilenen dosya/ekran belli ve "
        "test edilebilir kabul kriteri var — geliştirici ek soru sormadan başlayabilir.\n"
        "'detay' = muğlak/üst seviye, kapsam veya kabul kriteri eksik, teknik yaklaşım belirsiz "
        "ya da birden çok yoruma açık — önce teknik analiz gerekir.\n\n"
        "ÖNEMLİ: 'gerekce' o görevin İÇERİĞİNE özgü, somut bir tek cümle olmalı "
        "(örn. \"Etkilenen dosyalar ve i18n anahtarları net, kabul kriteri test edilebilir\" / "
        "\"Endpoint sözleşmesi ve hata durumları tanımsız\"). Genel/kalıp cümle YAZMA.\n"
        "Sana deterministik bir 'yapisal_hazir' ipucu verilir; dikkate al ama kararı İÇERİKTEN ver.\n\n"
        "SADECE şu JSON formatında yanıt ver, başka metin yazma:\n"
        '{"sonuclar":[{"key":"PROJ-1","durum":"hazir|detay","gerekce":"içeriğe özgü tek cümle",'
        '"eksikler":["detay ise eksik olan somut şeyler"]}]}'
    )


def _json_ayikla(metin: str) -> dict:
    """AI yanıtından ilk JSON nesnesini güvenli ayıklar."""
    m = re.search(r"\{.*\}", metin, re.DOTALL)
    if not m:
        raise ValueError("AI yanıtında JSON bulunamadı")
    return json.loads(m.group(0))


_BOLUM_ETIKET = {"amac": "Amaç", "degisiklik": "Değişiklik", "referans": "Referans", "kabul": "Kabul kriteri"}


def _yapisal_gerekce(ys: dict) -> str:
    """Yapısal taramada NEYE göre karar verildiğini şeffaf gösterir (içerik
    incelemesi DEĞİL — format/bölüm tespiti)."""
    var = [_BOLUM_ETIKET[a] for a, v in ys["bolumler"].items() if v]
    if ys["dosya_ref"]:
        var.append("dosya ref")
    bulgu = ", ".join(var) if var else "yapılandırılmış içerik yok"
    return f"Yapısal ön-tarama (format): {bulgu}"


def _ai_siniflandir(gorevler: list[dict], parca_boyu: int = 30) -> dict:
    """Görevleri AI ile İÇERİKTEN sınıflandırır. Büyük listeyi parçalara böler
    (CLI'de tek dev çağrı yavaş + çıktı limiti riski). key→{durum,gerekce,eksikler}."""
    ai_map: dict[str, dict] = {}
    sistem = _siniflandirma_prompt()
    for i in range(0, len(gorevler), parca_boyu):
        parca = gorevler[i:i + parca_boyu]
        ozet = [{
            "key": g["key"],
            "summary": g["summary"],
            "description": g["description"][:900],
            "yapisal_hazir": g["yapisal"]["hazir_yapisal"],
        } for g in parca]
        mesajlar = [{"role": "user", "content": [
            {"type": "text", "text": "Alt görevler:\n\n" + json.dumps(ozet, ensure_ascii=False, indent=2)},
            {"type": "text", "text": "Her görevi İÇERİĞİNE göre sınıflandır ve belirtilen JSON formatında dön."},
        ]}]
        try:
            yanit = _api_cagri(sistem, mesajlar, max_tokens=MAX_TOKENS_KISA, thinking=False)
            for s in _json_ayikla(_metin_sikistir(yanit)).get("sonuclar", []):
                ai_map[s.get("key", "")] = s
        except Exception as e:
            print(f"  ⚠ AI sınıflandırma parçası başarısız ({i}-{i+len(parca)}), yapısala düşülüyor: {e}")
    return ai_map


def gorevleri_siniflandir(gorevler: list[dict], ai_kullan: bool = True) -> dict:
    """İki fazlı sınıflandırma. Her görevde 'kaynak' alanı kararın NEYE dayandığını
    belirtir ('yapisal' = format ön-tarama / 'ai' = içerik incelemesi):
      - ai_kullan=False (FAZ 1): yalnızca yapısal ön-tarama — anında, 0 token.
        Bölüm/dosya işaretlerine bakar; İÇERİĞİ İNCELEMEZ. Şeffaf gerekçe verir.
      - ai_kullan=True (FAZ 2): AI HER görevin içeriğini okuyup sınıflandırır
        (parçalara bölünmüş); kararı gerçek bir gerekçeyle döner. Yapısal sonuç
        AI başarısız olan görevler için fallback kalır."""
    if not gorevler:
        return {"hazir": [], "detay": []}

    for g in gorevler:
        g["yapisal"] = _yapisal_skor(g)

    ai_map = _ai_siniflandir(gorevler) if ai_kullan else {}

    hazir, detay = [], []
    for g in gorevler:
        ys = g["yapisal"]
        ai = ai_map.get(g["key"])
        if ai and ai.get("durum") in ("hazir", "detay"):
            g["durum"] = ai["durum"]
            g["gerekce"] = ai.get("gerekce", "") or "AI içerik incelemesi"
            g["eksikler"] = ai.get("eksikler", []) or []
            g["kaynak"] = "ai"
        else:
            g["durum"] = "hazir" if ys["hazir_yapisal"] else "detay"
            g["gerekce"] = _yapisal_gerekce(ys)
            g["eksikler"] = [] if ys["hazir_yapisal"] else \
                [_BOLUM_ETIKET[a] for a, v in ys["bolumler"].items() if not v]
            g["kaynak"] = "yapisal"
        (hazir if g["durum"] == "hazir" else detay).append(g)

    # 'yapisal' iç alanı UI'a gönderilmesin (sade JSON)
    for g in gorevler:
        g.pop("yapisal", None)

    return {"hazir": hazir, "detay": detay}


# ─── Özellik 1: Standart Formata Çevir ───────────────────────────────────────

def gorev_standart_formatla(gorev: dict) -> str:
    """Mevcut görev içeriğini agent'ın standart görev formatına çevirir (hızlı normalize).
    Yeni kapsam UYDURMAZ — yalnızca var olan içeriği yeniden yapılandırır."""
    sistem = (
        "Kıdemli teknik analistsin. Sana bir Jira görevinin mevcut başlık ve açıklaması "
        "verilecek. Bu içeriği AŞAĞIDAKİ standart formata yeniden yapılandır. "
        "YENİ kapsam, dosya, kural veya kabul kriteri UYDURMA — yalnızca var olan bilgiyi "
        "doğru bölümlere yerleştir. Eksik bölüm varsa başlığı koy ve '(belirtilmemiş)' yaz.\n\n"
        "Çıktıyı TEK bir XML bloğu içinde, Türkçe Markdown olarak ver:\n\n"
        f"<gorev>\n{STANDART_GOREV_SABLONU}\n</gorev>"
    )
    icerik = [
        {"type": "text", "text": f"### Görev: {gorev.get('key','')} — {gorev.get('summary','')}"},
        {"type": "text", "text": f"### Mevcut Açıklama\n\n{gorev.get('description','') or '(açıklama yok)'}"},
        {"type": "text", "text": "Yukarıdaki görevi standart formata çevir."},
    ]
    yanit = _api_cagri(sistem, [{"role": "user", "content": icerik}], max_tokens=MAX_TOKENS_KISA, thinking=False)
    return _xml_ayir(_metin_sikistir(yanit), "gorev")


# ─── Özellik 2: Teknik Analiz ile Detaylandır ────────────────────────────────

def gorev_analiz_et(gorev: dict) -> str:
    """Görevi teknik analiz motoruyla (teknik_analiz_rol + _bolumler promptları)
    detaylandırır. RAG referansları dahil edilir. Tek görev kapsamında çalışır."""
    rol = prompt_yukle("teknik_analiz_rol")
    bolumler = prompt_yukle("teknik_analiz_bolumler")
    # Açık sorular bölümünü Aşama-2 mantığıyla burada da çıkar (tek görev için sade tut)
    bolumler = re.sub(
        r"(?ims)^#{1,3}\s*\d+\.\s*(?:Açık Sorular|Karar Bekleyen Konular).*?(?=^#{1,3}\s|\Z)",
        "", bolumler,
    ).strip()
    sistem = (
        rol + "\n\n"
        "Sana TEK bir Jira görevi verildi; SADECE bu görevin kapsamı için teknik analiz "
        "üret. Kapsam dışı bölümlerde boş bölüm kuralını uygula.\n\n"
        f"<teknik_analiz>\n{bolumler}\n</teknik_analiz>"
    )

    stable_bloklar: list[dict] = []
    try:
        ref_dosyalar = referans_dosyalari_hazirla()
        if ref_dosyalar:
            ref_bloklari, _ = _ref_bloklari_olustur(ref_dosyalar)
            stable_bloklar.extend(ref_bloklari)
    except Exception as e:
        print(f"  ⚠ Referanslar dahil edilemedi: {e}")
    if stable_bloklar:
        stable_bloklar[-1]["cache_control"] = {"type": "ephemeral"}

    icerik = stable_bloklar + [
        {"type": "text", "text": f"### Analiz Edilecek Jira Görevi: {gorev.get('key','')}\n\n"
                                 f"**Başlık:** {gorev.get('summary','')}\n\n"
                                 f"**Açıklama:**\n{gorev.get('description','') or '(açıklama yok)'}"},
        {"type": "text", "text": "Bu görev için teknik analiz raporunu üret (açık sorular HARİÇ)."},
    ]
    yanit = _api_cagri(sistem, [{"role": "user", "content": icerik}],
                       max_tokens=MAX_TOKENS_COMBINED, thinking=extended_thinking_acik())
    return _xml_ayir(_metin_sikistir(yanit), "teknik_analiz")


# ─── Jira'ya Yaz (onaydan sonra) ─────────────────────────────────────────────

def gorev_jiraya_yaz(task_key: str, markdown: str, summary: str | None = None) -> bool:
    """Görevin description'ını markdown→ADF olarak günceller (üzerine yazar).
    İsteğe bağlı summary de güncellenir. Canonical atlassian_put kullanır."""
    task_key = (task_key or "").strip().upper()
    if not _ID_DESENI.match(task_key):
        raise ValueError(f"Geçersiz Jira anahtarı: '{task_key}'")
    fields = {"description": {"type": "doc", "version": 1, "content": markdown_to_adf(markdown)}}
    if summary:
        fields["summary"] = summary
    atlassian_put(f"/rest/api/3/issue/{task_key}", body={"fields": fields}, cloud_id=_cloud_id())
    return True
