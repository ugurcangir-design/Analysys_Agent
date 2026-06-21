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
    referans_dosyalari_hazirla, _ref_bloklari_olustur, load_context_filter,
    MAX_TOKENS_KISA, MAX_TOKENS_COMBINED,
)

# Hafif modelin tam kimliği — Standart Formatla için sonnet yerine kullanılır.
# CLAUDE.md ve jira_agent.py ile aynı haiku sürümü.
MODEL_HAFIF = "claude-haiku-4-5-20251001"

# ─── Meta-Not Temizleyici (Jira description'a sızmasın) ─────────────────────
# Modelin (her promptta yasakladığımız halde) bazen yazdığı içsel/yönlendirme
# notlarını çıktıdan siler. Yasak kalıplar:
#  - "> Not — 12. Karar Bekleyen Konular: ... AYRI bir adımda üretilir..."
#  - "Açık Sorular ayrı çıktıda detaylandırılmalıdır"
#  - "[K: ❓ Belirsiz] olarak işaretlenen maddeler ayrı çıktıda..."
_META_NOT_DESENLERI = [
    # Tüm satır: "> **Not — ...Karar Bekleyen Konular: ... AYRI bir adımda...**" türü
    re.compile(r"(?im)^\s*>?\s*\*?\*?Not[^\n]*(?:Karar Bekleyen Konular|Aç[ıi]k Sorular)[^\n]*ayr[ıi][^\n]*ad[ıi]mda[^\n]*\n?"),
    # "Açık Sorular ayrı çıktıda detaylandırılmalıdır" türü
    re.compile(r"(?im)^[^\n]*aç[ıi]k\s*sorular[^\n]*(ayr[ıi]\s*ç[ıi]kt[ıi]da|ayr[ıi]\s*dok[üu]mantasyonda)[^\n]*\n?"),
    # "[K: ❓ Belirsiz] olarak işaretlenen maddeler ayrı çıktıda..."
    re.compile(r"(?im)^[^\n]*\[K:\s*❓?\s*Belirsiz\][^\n]*ayr[ıi]\s*ç[ıi]kt[ıi]da[^\n]*\n?"),
]


def _meta_notlari_temizle(metin: str) -> str:
    """Üretilen markdown çıktısındaki içsel/yönlendirme notlarını siler.
    Bunlar promptta yasak olmasına rağmen bazen çıkıyor; Jira description'a
    gitmeden burada kesilir. Birden çok arka arkaya boş satır da sıkıştırılır."""
    for desen in _META_NOT_DESENLERI:
        metin = desen.sub("", metin)
    return re.sub(r"\n{3,}", "\n\n", metin).strip()

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
    alanlar = ["summary", "description", "status", "issuetype", "priority", "assignee", "parent", "comment"]

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
                # Comment'ler: ADF→metin + yazar/tarih (analist task detayında görsün)
                comments = []
                cdata = f.get("comment") or {}
                for c in (cdata.get("comments") if isinstance(cdata, dict) else cdata) or []:
                    body_metin = _adf_to_text(c.get("body")) if isinstance(c.get("body"), dict) else (c.get("body") or "")
                    yazar = (c.get("author") or {}).get("displayName", "")
                    tarih = (c.get("created") or "")[:10]  # YYYY-MM-DD
                    comments.append({"yazar": yazar, "tarih": tarih, "metin": body_metin.strip()})
                gorevler.append({
                    "key": issue["key"],
                    "summary": f.get("summary", ""),
                    "status": (f.get("status") or {}).get("name", ""),
                    "type": (f.get("issuetype") or {}).get("name", ""),
                    "priority": (f.get("priority") or {}).get("name", ""),
                    "assignee": (f.get("assignee") or {}).get("displayName", ""),
                    "description": desc_metin.strip(),
                    "comments": comments,
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

# ─── Benzer Task Tespiti (deterministik, 0 token) ────────────────────────────

_STOPWORDS = {
    "ve", "ile", "için", "de", "da", "bir", "bu", "şu", "the", "of", "for", "to", "in", "on",
    "fe", "be", "ui", "api",  # katman/genel etiketleri — sinyal değil
}
_TOKEN_DESENI = re.compile(r"[a-zA-Z0-9ğüşıöçĞÜŞİÖÇ]{3,}")


def _benzerlik_jetonlari(gorev: dict) -> set[str]:
    """Görevin başlığı + açıklamasının ilk 300 karakterinden token seti üretir.
    Stopword'ler ve 3'ten kısa kelimeler atılır."""
    metin = (gorev.get("summary", "") + " " + (gorev.get("description", "") or "")[:300]).lower()
    return {t for t in _TOKEN_DESENI.findall(metin) if t not in _STOPWORDS}


def benzer_gorevleri_isaretle(gorevler: list[dict], esik: float = 0.35) -> None:
    """Görev listesinde her görev için BENZER (Jaccard ≥ esik) olanları bulup
    g['benzerler'] = [{'key', 'summary', 'skor'}] olarak işaretler. Token harcamaz.
    O(n²) ama 100 görevde milisaniye düzeyinde."""
    setler = [(g, _benzerlik_jetonlari(g)) for g in gorevler]
    for g, s in setler:
        g["benzerler"] = []
        if len(s) < 4:  # çok az token varsa sinyal güvenilmez
            continue
        skorlar = []
        for h, sh in setler:
            if h is g or len(sh) < 4:
                continue
            kesisim = len(s & sh)
            birlesim = len(s | sh)
            if not birlesim:
                continue
            j = kesisim / birlesim
            if j >= esik:
                skorlar.append((j, h))
        skorlar.sort(reverse=True, key=lambda x: x[0])
        g["benzerler"] = [
            {"key": h["key"], "summary": h.get("summary", ""), "skor": round(j, 2)}
            for j, h in skorlar[:3]  # ilk 3 benzer yeter
        ]


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

    # Benzer içerik tespiti — deterministik, 0 token; her görev `benzerler` listesi alır
    benzer_gorevleri_isaretle(gorevler)

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
    """Mevcut görev içeriğini agent'ın standart 4-başlık görev formatına çevirir.
    Hafif iş → haiku (Sonnet'in ~%10 maliyeti). YENİ kapsam UYDURMAZ; sadece var
    olan içeriği yeniden yapılandırır + boş bölüme '(belirtilmemiş)' notu yazar."""
    sistem = (
        "Kıdemli teknik analistsin. Sana bir Jira görevinin mevcut başlık ve açıklaması "
        "verilecek. Bu içeriği AŞAĞIDAKİ standart 4-başlık formata yeniden yapılandır.\n\n"
        "KURALLAR:\n"
        "1. YENİ kapsam/dosya/kural/kabul kriteri UYDURMA — yalnızca verilen bilgiyi "
        "doğru bölümlere yerleştir.\n"
        "2. Bir bölüm için bilgi yoksa başlığı KOY ve altına '(belirtilmemiş)' yaz "
        "(başlık varlığı + dolu/boş kuralı). Asla başlığı atlama, asla 'detay başka çıktıda' "
        "veya 'açık sorular ayrı dokümanda' türü notlar EKLEME — bu çıktı kendi kendine yeter.\n"
        "3. Yalnızca aşağıdaki 4 başlık bulunsun, ek bölüm ekleme.\n\n"
        "Çıktıyı TEK bir XML bloğu içinde, Türkçe Markdown olarak ver:\n\n"
        f"<gorev>\n{STANDART_GOREV_SABLONU}\n</gorev>"
    )
    icerik = [
        {"type": "text", "text": f"### Görev: {gorev.get('key','')} — {gorev.get('summary','')}"},
        {"type": "text", "text": f"### Mevcut Açıklama\n\n{gorev.get('description','') or '(açıklama yok)'}"},
        {"type": "text", "text": "Yukarıdaki görevi standart 4-başlık formata çevir."},
    ]
    yanit = _api_cagri(sistem, [{"role": "user", "content": icerik}],
                       model=MODEL_HAFIF, max_tokens=MAX_TOKENS_KISA, thinking=False)
    return _meta_notlari_temizle(_xml_ayir(_metin_sikistir(yanit), "gorev"))


# ─── Özellik 2: Teknik Analiz ile Detaylandır ────────────────────────────────

def gorev_analiz_et(gorev: dict) -> dict:
    """Görevi teknik analiz motoruyla (teknik_analiz_rol + _bolumler promptları)
    detaylandırır. İki aşama: (1) Sonnet ile detaylı teknik analiz (RAG dahil),
    (2) Haiku ile kısa açık-sorular pass'i. Çıktı:
        {"markdown": "<teknik analiz markdown>", "acik_sorular": "<varsa>"}.
    Açık sorular Jira'ya YAZILMAZ — UI'da ayrı sekmede gösterilir."""
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
        "ÖNEMLİ — KENDİ KENDİNE YETEN ÇIKTI:\n"
        "Açık sorular AYRI bir adımda üretilecek. Bu çıktıda 'Açık Sorular ayrı çıktıda "
        "detaylandırılmalıdır', 'detaylandırma gerekir', '[K: ❓ Belirsiz] olarak işaretlenen "
        "maddeler ayrı çıktıda...' türü meta-uyarı/yönlendirme NOTLARI YAZMA. Belirsizlik "
        "varsa metin içinde '[K: ❓ Belirsiz]' işaretle ve geç; ayrı bölüm/uyarı oluşturma.\n\n"
        f"<teknik_analiz>\n{bolumler}\n</teknik_analiz>"
    )

    # RAG: bağlam filtresi (Süreç Analizi ekranındaki filtre) ile filtrelenmiş
    # referansları topla. referans_dosyalari_hazirla() zaten load_context_filter()
    # + filtrele_referanslar() çağırıyor — atlamıyor. Burada ayrıca filtre durumunu
    # log ve çıktı meta yorumu için yakalıyoruz (analist şeffaflığı).
    ctx = load_context_filter() or {}
    aktif_filtreler = []
    if ctx.get("keywords"):         aktif_filtreler.append(f"kelime:{','.join(ctx['keywords'])}")
    if ctx.get("jira_keys"):        aktif_filtreler.append(f"jira:{','.join(ctx['jira_keys'])}")
    if ctx.get("confluence_pages"): aktif_filtreler.append(f"conf:{','.join(ctx['confluence_pages'])}")

    stable_bloklar: list[dict] = []
    referans_sayisi = 0
    try:
        ref_dosyalar = referans_dosyalari_hazirla()
        referans_sayisi = len(ref_dosyalar)
        if aktif_filtreler:
            print(f"  🔍 Bağlam filtresi aktif — {' | '.join(aktif_filtreler)}")
        print(f"  {referans_sayisi} referans dosya dahil ediliyor...")
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
        {"type": "text", "text": "Bu görev için teknik analiz raporunu üret (açık sorular HARİÇ — onlar ayrı adımda üretilecek)."},
    ]
    yanit = _api_cagri(sistem, [{"role": "user", "content": icerik}],
                       max_tokens=MAX_TOKENS_COMBINED, thinking=extended_thinking_acik())
    teknik = _meta_notlari_temizle(_xml_ayir(_metin_sikistir(yanit), "teknik_analiz"))

    # Şeffaflık: editör ön-izlemesinde + history'de RAG durumu görünür.
    # HTML yorumu olarak ekle — markdown render'da görünmez ama analist editörde okur.
    filtre_str = " | ".join(aktif_filtreler) if aktif_filtreler else "yok"
    teknik = (
        f"<!-- RAG: {referans_sayisi} referans dosya kullanıldı | bağlam filtresi: {filtre_str} -->\n\n"
        + teknik
    )

    # Aşama 2 — Açık Sorular (haiku, kısa). Hata olursa teknik analizi kaybetme.
    acik = ""
    try:
        acik = _gorev_acik_sorular_uret(teknik, gorev)
    except Exception as e:
        print(f"  ⚠ Görev açık soruları üretilemedi: {e}")

    return {"markdown": teknik, "acik_sorular": acik}


def _gorev_acik_sorular_uret(teknik_metni: str, gorev: dict) -> str:
    """Aşama-2 açık sorular: üretilen teknik analiz + görev kapsamına göre
    geliştirme ekibinin başlamadan netleştirmesi gereken sorular. Haiku — ucuz,
    hızlı. Çıktı Markdown; boşsa UI'da panel gizlenir."""
    sistem = (
        "Kıdemli teknik analistsin. Sana üretilmiş bir teknik analiz + ilgili Jira görevi "
        "verilecek. Geliştirme ekibinin kod yazmaya başlamadan önce netleştirmesi gereken "
        "açık soruları topla.\n\n"
        "KURALLAR:\n"
        "- Teknik analizde `[K: ❓ Belirsiz]` veya `⚠ VARSAYIM` işaretli her konuyu bir soruya çevir\n"
        "- Soru BAĞIMSIZ cevaplanabilir, tek konuya odaklı olmalı\n"
        "- Önem sırasına göre (Kritik → Yüksek → Orta → Düşük) sırala\n"
        "- Hiç gerçek belirsizlik yoksa SADECE şu satırı dön: 'Açık soru tespit edilmedi.'\n\n"
        "Çıktı Türkçe Markdown, XML bloğu içinde:\n\n"
        "<acik_sorular>\n"
        "### Q-T-001: [Başlık]\n"
        "- Önem: Kritik / Yüksek / Orta / Düşük\n"
        "- Bağlı bölüm: [§5 API / §4 DB / vb.]\n"
        "- Soru: [tek cümle]\n"
        "- Beklenen yanıt: [alan tipi / değer kümesi / karar]\n"
        "</acik_sorular>"
    )
    icerik = [
        {"type": "text", "text": f"### Üretilen Teknik Analiz\n\n{teknik_metni}"},
        {"type": "text", "text": f"### Kaynak Jira Görevi: {gorev.get('key','')}\n\n"
                                 f"**Başlık:** {gorev.get('summary','')}\n\n"
                                 f"**Açıklama:**\n{gorev.get('description','') or '(açıklama yok)'}"},
        {"type": "text", "text": "Yukarıdaki teknik analiz ve görevdeki tüm açık konuları soru olarak topla."},
    ]
    yanit = _api_cagri(sistem, [{"role": "user", "content": icerik}],
                       model=MODEL_HAFIF, max_tokens=MAX_TOKENS_KISA, thinking=False)
    return _xml_ayir(_metin_sikistir(yanit), "acik_sorular")


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
