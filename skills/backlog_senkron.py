"""Backlog Senkron — UAT board ↔ TRADE/OPS board takip motoru.

Amaç: Product'ın UAT board'unda (MBSUATEAM) açtığı taskların, bizim çalışma
board'larımızdaki (MBSTRADE / MBSOPS) karşılıklarını mevcut takip Excel'ine
işlemek; task durumlarını güncel tutmak. Analist her gün ekrandan tek tıkla
çalıştırır, güncel Excel'i indirir.

TASARIM İLKELERİ (kullanıcı talebi):
- **0 LLM tokenı.** Bu iş tamamen DETERMİNİSTİK veri eşleme — `claude -p`/MCP
  ÇAĞRILMAZ. Sadece Jira REST okuması + Excel yazımı. Saniyeler sürer.
- **Değişmeyene iş yapma.** Her satırın Jira `updated` damgası, yan durum
  dosyasındaki son değerle kıyaslanır; DEĞİŞMEMİŞSE o satıra tek hücre yazılmaz.
- **Manuel notlara dokunma.** Yalnızca Jira'dan gelen kolonlar (Özet, Konu Türü,
  Durum, Öncelik, Oluşturulan, Güncellendi, Etiketler) ve agent'a ait yeni UAT
  kolonları yazılır. Diğer TÜM kolonlar (İlgili Analist, Priority, UAT BOARD
  [kolon Q], Status, Product Onayı, Bağımlılık/Not, Eski Task Ekran Görüntüsü …)
  hiç okunmaz/yazılmaz.
- **Dosyayı BOZMA.** Excel'de hücre-içi görseller (richData), Excel Tablosu,
  hyperlink'ler ve gizli sayfalar var. openpyxl bunları kaydederken DÜŞÜRÜR.
  Bu yüzden yazım CERRAHİDİR: zip içinde YALNIZCA hedef sayfanın XML'i değişir,
  medya/richData/diğer sayfalar/tablo bit-bit korunur. Orijinalin üstüne yazılmaz;
  zaman damgalı KOPYA üretilir.

Bağ mekanizması (Jira ile doğrulandı): UAT taskı --"relates to"--> TRADE/OPS taskı.
Bir UAT birden çok TRADE/OPS taskına bağlanabilir; her TRADE/OPS taskı = bir satır.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook

from .atlassian import atlassian_post
from .jira_gorevleri import _cloud_id

logger = logging.getLogger("analyst.backlog_senkron")

# ─── Sabitler ──────────────────────────────────────────────────────────────────
KAYNAK_SHEET = "Excel Maddeleri"   # ana takip sayfası
HEADER_SATIR = 3                    # başlıklar bu satırda; veri HEADER_SATIR+1'den
KEY_BASLIK = "TRADE/OPERATION BOARD"
SIRA_BASLIK = "Sıra"
ALAN_BASLIK = "Alan"               # FE/BE — yalnızca boşsa doldurulur

# Jira'dan gelen kolonlar: {Excel başlığı → issue alan anahtarı}. Agent bunları yazar.
JIRA_KOLON_ESLEME = {
    "Özet": "summary",
    "Konu Türü": "issuetype",
    "Durum": "status",
    "Öncelik": "priority",
    "Oluşturulan": "created",
    "Güncellendi": "updated",
    "Etiketler": "labels",
}
# Agent'a ait UAT kolonları (yoksa sağa eklenir; başlık adından tanınır → idempotent).
UAT_KEY_BASLIK = "UAT Key"
UAT_DURUM_BASLIK = "UAT Durum"
UAT_OZET_BASLIK = "UAT Özet"
UAT_BASLIKLAR = [UAT_KEY_BASLIK, UAT_DURUM_BASLIK, UAT_OZET_BASLIK]

CALISMA_ONEKLERI = ("MBSTRADE", "MBSOPS")
UAT_PROJE = "MBSUATEAM"

_BULKFETCH_LIMIT = 100
_TR_AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz",
             "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


# ─── Jira / biçim yardımcıları ──────────────────────────────────────────────────
def _tarih_tr(iso: str) -> str:
    """ISO tarihi Excel'deki görünüm biçimine çevirir: '04/Haz/26 6:46 PM'."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return iso
    saat = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.day:02d}/{_TR_AYLAR[dt.month - 1]}/{dt.strftime('%y')} {saat}:{dt.minute:02d} {ampm}"


def _alan_turet(summary: str) -> str:
    """Özet önekinden FE/BE türetir ('FE — ...' → 'FE'). Belirsizse boş."""
    s = (summary or "").lstrip()
    if s[:2].upper() == "FE":
        return "FE"
    if s[:2].upper() == "BE":
        return "BE"
    return ""


def _issue_alanlari(f: dict) -> dict:
    """Ham Jira issue.fields → Excel'e yazılacak sade sözlük."""
    labels = f.get("labels") or []
    return {
        "summary": f.get("summary") or "",
        "issuetype": (f.get("issuetype") or {}).get("name", ""),
        "status": (f.get("status") or {}).get("name", ""),
        "priority": (f.get("priority") or {}).get("name", ""),
        "created": _tarih_tr(f.get("created") or ""),
        "updated": _tarih_tr(f.get("updated") or ""),
        "labels": " | ".join(labels),
        "_updated_iso": f.get("updated") or "",
    }


def _uat_board_tara(cloud_id: str) -> dict[str, dict]:
    """UAT board'unu (MBSUATEAM) tarar; TRADE/OPS key → UAT bilgisi eşlemesi döndürür."""
    eslesme: dict[str, dict] = {}
    page_token = None
    sayfa = 0
    while True:
        body = {
            "jql": f"project = {UAT_PROJE} ORDER BY key ASC",
            "fields": ["summary", "status", "issuelinks"],
            "maxResults": 100,
        }
        if page_token:
            body["nextPageToken"] = page_token
        data = atlassian_post("/rest/api/3/search/jql", body, cloud_id=cloud_id)
        for iss in data.get("issues", []):
            uf = iss.get("fields", {})
            uat_key = iss.get("key", "")
            uat_durum = (uf.get("status") or {}).get("name", "")
            uat_ozet = uf.get("summary") or ""
            for lk in (uf.get("issuelinks") or []):
                for side in ("outwardIssue", "inwardIssue"):
                    o = lk.get(side)
                    if not o:
                        continue
                    tkey = o.get("key", "")
                    if not tkey.startswith(CALISMA_ONEKLERI):
                        continue
                    kayit = eslesme.setdefault(
                        tkey, {"uat_keys": [], "uat_durumlar": [], "uat_ozetler": []})
                    if uat_key not in kayit["uat_keys"]:
                        kayit["uat_keys"].append(uat_key)
                        kayit["uat_durumlar"].append(uat_durum)
                        kayit["uat_ozetler"].append(uat_ozet)
        sayfa += 1
        page_token = data.get("nextPageToken")
        if data.get("isLast") or not page_token or sayfa > 20:
            break
    for kayit in eslesme.values():
        kayit["uat_key"] = " | ".join(kayit["uat_keys"])
        kayit["uat_durum"] = " | ".join(kayit["uat_durumlar"])
        kayit["uat_ozet"] = " | ".join(dict.fromkeys(kayit["uat_ozetler"]))
    logger.info("UAT board tarandı: %d sayfa, %d çalışma-taskı eşleşmesi", sayfa, len(eslesme))
    return eslesme


def _calisma_tasklari_getir(keys: list[str], cloud_id: str) -> dict[str, dict]:
    """TRADE/OPS key listesini bulkfetch ile taze okur (100'lük batch). LLM YOK."""
    sonuc: dict[str, dict] = {}
    alanlar = ["summary", "status", "issuetype", "priority", "created", "updated", "labels"]
    for i in range(0, len(keys), _BULKFETCH_LIMIT):
        batch = keys[i:i + _BULKFETCH_LIMIT]
        data = atlassian_post(
            "/rest/api/3/issue/bulkfetch",
            {"issueIdsOrKeys": batch, "fields": alanlar},
            cloud_id=cloud_id,
        )
        for iss in data.get("issues", []):
            sonuc[iss.get("key", "")] = _issue_alanlari(iss.get("fields", {}))
    return sonuc


# ─── Excel okuma (openpyxl, salt-okuma) ─────────────────────────────────────────
def _baslik_haritasi(ws) -> dict[str, int]:
    harita = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(HEADER_SATIR, c).value
        if v is not None and str(v).strip():
            harita[str(v).strip()] = c
    return harita


# ─── Kolon harfi <-> indeks ─────────────────────────────────────────────────────
def _kolon_harf(idx: int) -> str:
    s = ""
    while idx > 0:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def _harf_kolon(ref: str) -> int:
    harf = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in harf:
        n = n * 26 + (ord(ch) - 64)
    return n


# ─── Cerrahi XML yazımı ─────────────────────────────────────────────────────────
def _sheet_part_bul(zf: zipfile.ZipFile, sheet_adi: str) -> str:
    """workbook.xml + rels üzerinden sayfa adına karşılık gelen part yolunu bulur."""
    wb = etree.fromstring(zf.read("xl/workbook.xml"))
    rid = None
    for s in wb.find(f"{{{_NS}}}sheets"):
        if s.get("name") == sheet_adi:
            rid = s.get(f"{{{_NS_R}}}id")
            break
    if not rid:
        raise ValueError(f"'{sheet_adi}' sayfası workbook.xml'de yok")
    rels = etree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.get("Id") == rid:
            target = rel.get("Target")
            return "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
    raise ValueError(f"{rid} için rels hedefi bulunamadı")


def _surgical_yaz(kaynak: Path, cikti: Path, sheet_adi: str,
                  yazimlar: dict[tuple[int, int], str]) -> None:
    """`yazimlar` = {(satir, kolon_idx): metin}. YALNIZCA hedef sayfanın XML'i
    değişir; medya, richData, tablo, hyperlink'ler, diğer sayfalar korunur."""
    with zipfile.ZipFile(kaynak) as zf:
        part = _sheet_part_bul(zf, sheet_adi)
        sheet_xml = zf.read(part)
        infolist = zf.infolist()
        icerikler = {i.filename: zf.read(i.filename) for i in infolist}

    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f"{{{_NS}}}sheetData")
    row_map = {int(r.get("r")): r for r in sheet_data.findall(f"{{{_NS}}}row")}

    def satir_al(n: int):
        if n in row_map:
            return row_map[n]
        yeni = etree.Element(f"{{{_NS}}}row")
        yeni.set("r", str(n))
        yerlesti = False
        for mevcut in sheet_data.findall(f"{{{_NS}}}row"):
            if int(mevcut.get("r")) > n:
                mevcut.addprevious(yeni)
                yerlesti = True
                break
        if not yerlesti:
            sheet_data.append(yeni)
        row_map[n] = yeni
        return yeni

    def ust_stil(col_idx: int, satir: int) -> str | None:
        """Yeni hücreye üstteki (aynı kolon) hücrenin stilini kopyala — biçim tutarlılığı."""
        for r in range(satir - 1, HEADER_SATIR, -1):
            re_el = row_map.get(r)
            if re_el is None:
                continue
            ref = f"{_kolon_harf(col_idx)}{r}"
            for c in re_el.findall(f"{{{_NS}}}c"):
                if c.get("r") == ref:
                    return c.get("s")
            break
        return None

    def hucre_yaz(satir: int, col_idx: int, metin: str):
        row_el = satir_al(satir)
        ref = f"{_kolon_harf(col_idx)}{satir}"
        hedef = None
        for c in row_el.findall(f"{{{_NS}}}c"):
            if c.get("r") == ref:
                hedef = c
                break
        created = hedef is None
        if created:
            hedef = etree.Element(f"{{{_NS}}}c")
            hedef.set("r", ref)
            yerlesti = False
            for c in row_el.findall(f"{{{_NS}}}c"):
                if _harf_kolon(c.get("r")) > col_idx:
                    c.addprevious(hedef)
                    yerlesti = True
                    break
            if not yerlesti:
                row_el.append(hedef)
            stil = ust_stil(col_idx, satir)
            if stil:
                hedef.set("s", stil)
        # İçeriği temizle (<v>, <f>, eski <is>) ve inlineStr olarak yaz.
        for ch in list(hedef):
            hedef.remove(ch)
        hedef.set("t", "inlineStr")
        is_el = etree.SubElement(hedef, f"{{{_NS}}}is")
        t_el = etree.SubElement(is_el, f"{{{_NS}}}t")
        t_el.text = metin
        t_el.set(_XML_SPACE, "preserve")

    for (satir, col), metin in sorted(yazimlar.items()):
        hucre_yaz(satir, col, metin)

    # dimension güncelle
    if yazimlar:
        max_row = max(max(row_map), max(s for s, _ in yazimlar))
        max_col = max((c for _, c in yazimlar), default=1)
        # mevcut dimension'daki kolonu da hesaba kat
        dim = root.find(f"{{{_NS}}}dimension")
        if dim is not None:
            eski = dim.get("ref", "A1")
            son = eski.split(":")[-1]
            max_col = max(max_col, _harf_kolon(son))
            max_row = max(max_row, int(re.search(r"\d+", son).group(0)))
            dim.set("ref", f"A1:{_kolon_harf(max_col)}{max_row}")

    yeni_sheet = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    icerikler[part] = yeni_sheet

    with zipfile.ZipFile(cikti, "w", zipfile.ZIP_DEFLATED) as zf:
        for info in infolist:
            zf.writestr(info, icerikler[info.filename])


# ─── Durum dosyası ──────────────────────────────────────────────────────────────
def _durum_oku(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _durum_yaz(state_path: Path, veri: dict) -> None:
    state_path.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Ana giriş ──────────────────────────────────────────────────────────────────
def senkronize_et(excel_path: str | Path, cikti_dir: str | Path,
                  state_path: str | Path | None = None) -> dict:
    """Excel'i Jira ile senkronize eder, zaman damgalı KOPYA üretir."""
    excel_path = Path(excel_path)
    cikti_dir = Path(cikti_dir)
    cikti_dir.mkdir(parents=True, exist_ok=True)
    if state_path is None:
        state_path = cikti_dir / "backlog_senkron_state.json"
    state_path = Path(state_path)

    # ── Okuma (openpyxl salt-okuma; ASLA save edilmez) ──
    wb = load_workbook(excel_path, data_only=True)
    if KAYNAK_SHEET not in wb.sheetnames:
        raise ValueError(f"Excel'de '{KAYNAK_SHEET}' sayfası yok. Sayfalar: {wb.sheetnames}")
    ws = wb[KAYNAK_SHEET]
    basliklar = _baslik_haritasi(ws)
    if KEY_BASLIK not in basliklar:
        raise ValueError(f"'{KEY_BASLIK}' kolonu bulunamadı. Başlıklar: {list(basliklar)}")

    uyarilar = [f"'{b}' kolonu Excel'de yok — güncellenmeyecek."
                for b in JIRA_KOLON_ESLEME if b not in basliklar]

    # UAT kolonları: varsa yeniden kullan, yoksa GERÇEK son kolonun ötesine yeni
    # indeks ata. ws.max_column'u da hesaba kat — başlıksız ama dolu kolonların
    # (ör. X'teki serbest veriler) üstüne yazmayı önler.
    max_col = max(max(basliklar.values()), ws.max_column)
    for b in UAT_BASLIKLAR:
        if b not in basliklar:
            max_col += 1
            basliklar[b] = max_col

    key_c = basliklar[KEY_BASLIK]
    sira_c = basliklar.get(SIRA_BASLIK)
    alan_c = basliklar.get(ALAN_BASLIK)

    key_satir: dict[str, int] = {}
    son_veri_satir = HEADER_SATIR
    en_yuksek_sira = 0
    alan_bos: dict[str, bool] = {}
    for r in range(HEADER_SATIR + 1, ws.max_row + 1):
        dolu = any(ws.cell(r, c).value not in (None, "") for c in range(1, ws.max_column + 1))
        if dolu:
            son_veri_satir = r
        k = ws.cell(r, key_c).value
        if k is not None and str(k).strip():
            key = str(k).strip()
            key_satir[key] = r
            alan_bos[key] = (alan_c is not None and ws.cell(r, alan_c).value in (None, ""))
        if sira_c:
            try:
                en_yuksek_sira = max(en_yuksek_sira, int(ws.cell(r, sira_c).value))
            except (ValueError, TypeError):
                pass

    # ── Jira'dan taze veri ──
    cloud_id = _cloud_id()
    uat_eslesme = _uat_board_tara(cloud_id)
    hedef_keys = {k for k in (set(key_satir) | set(uat_eslesme)) if k.startswith(CALISMA_ONEKLERI)}
    jira = _calisma_tasklari_getir(sorted(hedef_keys), cloud_id)

    durum = _durum_oku(state_path)
    guncellenen = eklenen = degismeyen = yeni_uat = 0
    yazimlar: dict[tuple[int, int], str] = {}

    # Eksik UAT başlıklarını yaz (yeni eklenen kolonların başlığı)
    for b in UAT_BASLIKLAR:
        # her zaman garanti et (idempotent): başlık hücresi zaten varsa aynı metin yazılır
        yazimlar[(HEADER_SATIR, basliklar[b])] = b

    def _satir_hucreleri(satir: int, key: str, alanlar: dict, uat: dict | None, alan_bos_mu: bool):
        for baslik, alan in JIRA_KOLON_ESLEME.items():
            c = basliklar.get(baslik)
            if c:
                yazimlar[(satir, c)] = alanlar.get(alan, "")
        if alan_c and alan_bos_mu:
            t = _alan_turet(alanlar.get("summary", ""))
            if t:
                yazimlar[(satir, alan_c)] = t
        if uat:
            yazimlar[(satir, basliklar[UAT_KEY_BASLIK])] = uat.get("uat_key", "")
            yazimlar[(satir, basliklar[UAT_DURUM_BASLIK])] = uat.get("uat_durum", "")
            yazimlar[(satir, basliklar[UAT_OZET_BASLIK])] = uat.get("uat_ozet", "")

    # Mevcut satırlar — yalnızca değişenler
    for key, r in key_satir.items():
        if key not in jira:
            continue
        alanlar = jira[key]
        yeni_iso = alanlar.get("_updated_iso", "")
        uat = uat_eslesme.get(key)
        uat_key_str = uat.get("uat_key", "") if uat else ""
        onceki = durum.get(key, {})
        uat_degisti = uat_key_str != onceki.get("uat_key", "")
        if yeni_iso and yeni_iso == onceki.get("updated") and not uat_degisti:
            degismeyen += 1
            continue
        _satir_hucreleri(r, key, alanlar, uat, alan_bos.get(key, False))
        durum[key] = {"updated": yeni_iso, "uat_key": uat_key_str}
        guncellenen += 1
        if uat_degisti and uat_key_str:
            yeni_uat += 1

    # Yeni satırlar (UAT'tan keşfedilip Excel'de olmayanlar)
    yeni_keys = sorted(k for k in uat_eslesme if k not in key_satir and k in jira)
    for key in yeni_keys:
        son_veri_satir += 1
        r = son_veri_satir
        en_yuksek_sira += 1
        if sira_c:
            yazimlar[(r, sira_c)] = str(en_yuksek_sira)
        yazimlar[(r, key_c)] = key
        _satir_hucreleri(r, key, jira[key], uat_eslesme.get(key), True)
        durum[key] = {"updated": jira[key].get("_updated_iso", ""),
                      "uat_key": uat_eslesme.get(key, {}).get("uat_key", "")}
        eklenen += 1

    # ── Yazım ──
    damga = datetime.now().strftime("%Y-%m-%d_%H%M")
    taban = re.sub(r"_\d{4}-\d{2}-\d{2}_\d{4}$", "", excel_path.stem)
    cikti_ad = f"{taban}_{damga}.xlsx"
    cikti_yol = cikti_dir / cikti_ad

    if guncellenen == 0 and eklenen == 0:
        # Hiç değişiklik yok → sadece orijinali kopyala (yazma bile yapma)
        shutil.copyfile(excel_path, cikti_yol)
    else:
        _surgical_yaz(excel_path, cikti_yol, KAYNAK_SHEET, yazimlar)

    _durum_yaz(state_path, durum)

    return {
        "ok": True,
        "cikti_dosya": cikti_ad,
        "guncellenen": guncellenen,
        "eklenen": eklenen,
        "degismeyen": degismeyen,
        "yeni_uat_baglantisi": yeni_uat,
        "uyarilar": uyarilar,
        "sheet": KAYNAK_SHEET,
        "toplam_satir": len(key_satir) + eklenen,
    }
