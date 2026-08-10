"""Backlog Senkron — UAT board ↔ TRADE/OPS board takip motoru.

Amaç: Product'ın UAT board'unda (MBSUATEAM) açtığı taskların, bizim çalışma
board'larımızdaki (MBSTRADE / MBSOPS) karşılıklarını mevcut takip Excel'ine
işlemek; task durumlarını güncel tutmak. Analist her gün ekrandan tek tıkla
çalıştırır, güncel Excel'i indirir.

TASARIM İLKELERİ (kullanıcı talebi):
- **0 LLM tokenı.** Tamamen DETERMİNİSTİK veri eşleme — `claude -p`/MCP ÇAĞRILMAZ.
  Sadece Jira REST okuması + Excel yazımı. Saniyeler sürer.
- **Değişmeyene iş yapma.** Yan durum dosyasında her key'in son `updated`+`uat_key`
  değeri tutulur; değişmemiş satıra tek hücre yazılmaz. Hiç değişiklik yoksa dosya
  yalnızca kopyalanır.
- **Manuel notlara dokunma.** Yalnızca Jira kolonları (Özet, Konu Türü, Durum,
  Öncelik, Oluşturulan, Güncellendi, Etiketler) + agent'a ait UAT kolonları yazılır.
  Diğer TÜM kolonlar (İlgili Analist, Priority, Öncelik Grubu, Efor Skoru, UAT BOARD
  [kolon Q], Status, Product Onayı, Bağımlılık/Not, Açıklama Kısa, Eski Task Ekran
  Görüntüsü) hiç okunmaz/yazılmaz.
- **EXCEL FORMUNU KORU (KRİTİK).** Excel'de hücre-içi görseller (richData/`vm=`),
  Excel Tablosu (ListObject — renk bandı + filtre), hyperlink'ler ve gizli sayfalar
  var. openpyxl kaydederken bunları DÜŞÜRÜR. Bu yüzden:
    * Yazım `lxml` ile CERRAHİDİR: zip içinde YALNIZCA hedef sayfa + tablo XML'i
      değişir; medya/richData/metadata/diğer sayfalar bit-bit korunur.
    * Yeni satırlar/kolonlar TABLONUN İÇİNE alınır: UAT kolonları tabloya bitişik
      (W'den sonra) eklenir, yeni satırlar önce boş rezerve slotlara yerleşir sonra
      alta eklenir, tablo `ref`+`autoFilter` genişletilir → renk bandı ve filtre
      yeni satır/kolonları da kapsar (yönetilebilir liste).
  Orijinalin üstüne yazılmaz; zaman damgalı KOPYA üretilir.

Bağ mekanizması (Jira ile doğrulandı): UAT taskı --"relates to"--> TRADE/OPS taskı.
Bir UAT birden çok TRADE/OPS taskına bağlanabilir; her TRADE/OPS taskı = bir satır.
"""
from __future__ import annotations

import json
import logging
import posixpath
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import range_boundaries

from .atlassian import atlassian_post
from .jira_gorevleri import _cloud_id

logger = logging.getLogger("analyst.backlog_senkron")

# ─── Sabitler ──────────────────────────────────────────────────────────────────
KAYNAK_SHEET = "Excel Maddeleri"
HEADER_SATIR = 3
KEY_BASLIK = "TRADE/OPERATION BOARD"
SIRA_BASLIK = "Sıra"
ALAN_BASLIK = "Alan"

JIRA_KOLON_ESLEME = {
    "Özet": "summary",
    "Konu Türü": "issuetype",
    "Durum": "status",
    "Öncelik": "priority",
    "Oluşturulan": "created",
    "Güncellendi": "updated",
    "Etiketler": "labels",
}
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
    s = (summary or "").lstrip()
    if s[:2].upper() == "FE":
        return "FE"
    if s[:2].upper() == "BE":
        return "BE"
    return ""


def _issue_alanlari(f: dict) -> dict:
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
    """UAT board'unu (MBSUATEAM) tarar; TRADE/OPS key → UAT bilgisi eşlemesi."""
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


# ─── Kolon harfi <-> indeks ─────────────────────────────────────────────────────
def _kolon_harf(idx: int) -> str:
    s = ""
    while idx > 0:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def _harf_kolon(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + (ord(ch) - 64)
    return n


def _baslik_haritasi(ws) -> dict[str, int]:
    harita = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(HEADER_SATIR, c).value
        if v is not None and str(v).strip():
            harita[str(v).strip()] = c
    return harita


# ─── Zip / XML cerrahi yazım ────────────────────────────────────────────────────
def _sheet_part_bul(zf: zipfile.ZipFile, sheet_adi: str) -> str:
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
            t = rel.get("Target")
            return "xl/" + t.lstrip("/") if not t.startswith("xl/") else t
    raise ValueError(f"{rid} için rels hedefi bulunamadı")


def _tablo_part_bul(zf: zipfile.ZipFile, sheet_part: str) -> str | None:
    """Sayfaya bağlı ilk Excel Tablosu (ListObject) part yolunu döndürür (yoksa None)."""
    root = etree.fromstring(zf.read(sheet_part))
    tps = root.find(f"{{{_NS}}}tableParts")
    if tps is None or len(tps) == 0:
        return None
    rid = tps[0].get(f"{{{_NS_R}}}id")
    rels_yol = posixpath.join(posixpath.dirname(sheet_part), "_rels",
                              posixpath.basename(sheet_part) + ".rels")
    rels = etree.fromstring(zf.read(rels_yol))
    for rel in rels:
        if rel.get("Id") == rid:
            hedef = rel.get("Target")
            return posixpath.normpath(posixpath.join(posixpath.dirname(sheet_part), hedef))
    return None


def _tablo_xml_uygula(tablo_bytes: bytes, yeni_ref: str, yeni_kolon_adlari: list[str]) -> bytes:
    """Tablo XML'inde ref+autoFilter'ı genişletir ve eksik tableColumn'ları ekler."""
    root = etree.fromstring(tablo_bytes)
    root.set("ref", yeni_ref)
    af = root.find(f"{{{_NS}}}autoFilter")
    if af is not None:
        af.set("ref", yeni_ref)
    tcs = root.find(f"{{{_NS}}}tableColumns")
    mevcut_adlar = {tc.get("name") for tc in tcs.findall(f"{{{_NS}}}tableColumn")}
    max_id = max(int(tc.get("id")) for tc in tcs.findall(f"{{{_NS}}}tableColumn"))
    for ad in yeni_kolon_adlari:
        if ad not in mevcut_adlar:
            max_id += 1
            tc = etree.SubElement(tcs, f"{{{_NS}}}tableColumn")
            tc.set("id", str(max_id))
            tc.set("name", ad)
            mevcut_adlar.add(ad)
    tcs.set("count", str(len(tcs.findall(f"{{{_NS}}}tableColumn"))))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _surgical_yaz(kaynak: Path, cikti: Path, sheet_adi: str,
                  yazimlar: dict[tuple[int, int], str],
                  tablo_ref: str | None = None,
                  tablo_yeni_kolonlar: list[str] | None = None) -> None:
    """`yazimlar` = {(satir, kolon_idx): metin}. YALNIZCA hedef sayfa (+ varsa tablo)
    XML'i değişir; medya, richData, tablo görselleri, diğer sayfalar korunur."""
    with zipfile.ZipFile(kaynak) as zf:
        part = _sheet_part_bul(zf, sheet_adi)
        sheet_xml = zf.read(part)
        tablo_part = _tablo_part_bul(zf, part) if tablo_ref else None
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
        if hedef is None:
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
        dim = root.find(f"{{{_NS}}}dimension")
        if dim is not None:
            son = dim.get("ref", "A1").split(":")[-1]
            max_col = max(max_col, _harf_kolon(son))
            max_row = max(max_row, int(re.search(r"\d+", son).group(0)))
            dim.set("ref", f"A1:{_kolon_harf(max_col)}{max_row}")

    icerikler[part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    # Tabloyu genişlet (renk bandı + filtre yeni satır/kolonları kapsasın)
    if tablo_ref and tablo_part and tablo_part in icerikler:
        icerikler[tablo_part] = _tablo_xml_uygula(
            icerikler[tablo_part], tablo_ref, tablo_yeni_kolonlar or [])

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

    wb = load_workbook(excel_path, data_only=True)
    if KAYNAK_SHEET not in wb.sheetnames:
        raise ValueError(f"Excel'de '{KAYNAK_SHEET}' sayfası yok. Sayfalar: {wb.sheetnames}")
    ws = wb[KAYNAK_SHEET]
    basliklar = _baslik_haritasi(ws)
    if KEY_BASLIK not in basliklar:
        raise ValueError(f"'{KEY_BASLIK}' kolonu bulunamadı. Başlıklar: {list(basliklar)}")

    uyarilar = [f"'{b}' kolonu Excel'de yok — güncellenmeyecek."
                for b in JIRA_KOLON_ESLEME if b not in basliklar]

    # ── Excel Tablosu geometrisi ──
    tablo = next(iter(ws.tables.values()), None) if ws.tables else None
    if tablo is not None:
        t_c1, t_r1, t_c2, t_r2 = range_boundaries(tablo.ref)   # min_col,min_row,max_col,max_row
    else:
        t_c1, t_r1, t_c2, t_r2 = 1, HEADER_SATIR, max(basliklar.values()), ws.max_row

    # ── UAT kolonları: varsa yeniden kullan (başlıktan), yoksa TABLOYA BİTİŞİK ekle ──
    sonraki_kol = t_c2
    for b in UAT_BASLIKLAR:
        if b in basliklar:
            sonraki_kol = max(sonraki_kol, basliklar[b])
        else:
            sonraki_kol += 1
            basliklar[b] = sonraki_kol
    uat_son_kol = max(basliklar[b] for b in UAT_BASLIKLAR)

    key_c = basliklar[KEY_BASLIK]
    sira_c = basliklar.get(SIRA_BASLIK)
    alan_c = basliklar.get(ALAN_BASLIK)

    # ── Mevcut satırlar + boş rezerve slotlar ──
    key_satir: dict[str, int] = {}
    alan_bos: dict[str, bool] = {}
    en_yuksek_sira = 0
    bos_slotlar: list[int] = []
    for r in range(HEADER_SATIR + 1, max(t_r2, ws.max_row) + 1):
        k = ws.cell(r, key_c).value
        if k is not None and str(k).strip():
            key = str(k).strip()
            key_satir[key] = r
            alan_bos[key] = (alan_c is not None and ws.cell(r, alan_c).value in (None, ""))
        elif r <= t_r2:
            # Tablo içi, key'siz VE (Sıra hariç) tamamen boş satır → doldurulabilir slot
            if all(ws.cell(r, c).value in (None, "") for c in range(1, t_c2 + 1) if c != sira_c):
                bos_slotlar.append(r)
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

    # UAT başlık hücreleri (idempotent: zaten varsa aynı metin)
    for b in UAT_BASLIKLAR:
        yazimlar[(HEADER_SATIR, basliklar[b])] = b

    def _satir_hucreleri(satir: int, alanlar: dict, uat: dict | None, alan_bos_mu: bool):
        for baslik, alan in JIRA_KOLON_ESLEME.items():
            c = basliklar.get(baslik)
            if c:
                yazimlar[(satir, c)] = alanlar.get(alan, "")
        if alan_c and alan_bos_mu:
            t = _alan_turet(alanlar.get("summary", ""))
            if t:
                yazimlar[(satir, alan_c)] = t
        # UAT kolonları HER ZAMAN yazılır (eşleşme yoksa boş → eski/çöp değer temizlenir)
        yazimlar[(satir, basliklar[UAT_KEY_BASLIK])] = uat.get("uat_key", "") if uat else ""
        yazimlar[(satir, basliklar[UAT_DURUM_BASLIK])] = uat.get("uat_durum", "") if uat else ""
        yazimlar[(satir, basliklar[UAT_OZET_BASLIK])] = uat.get("uat_ozet", "") if uat else ""

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
        _satir_hucreleri(r, alanlar, uat, alan_bos.get(key, False))
        durum[key] = {"updated": yeni_iso, "uat_key": uat_key_str}
        guncellenen += 1
        if uat_degisti and uat_key_str:
            yeni_uat += 1

    # Yeni satırlar — önce boş rezerve slotlar, sonra tablonun altına ekle
    yeni_keys = sorted(k for k in uat_eslesme if k not in key_satir and k in jira)
    slot_iter = iter(bos_slotlar)
    ek_satir = t_r2   # tablonun mevcut son satırı; altına eklemeye buradan devam
    for key in yeni_keys:
        r = next(slot_iter, None)
        if r is None:
            ek_satir += 1
            r = ek_satir
        # Sıra: slotta varsa koru, yoksa sıradaki numarayı ata
        mevcut_sira = ws.cell(r, sira_c).value if (sira_c and r <= ws.max_row) else None
        if sira_c and (mevcut_sira in (None, "")):
            en_yuksek_sira += 1
            yazimlar[(r, sira_c)] = str(en_yuksek_sira)
        yazimlar[(r, key_c)] = key
        _satir_hucreleri(r, jira[key], uat_eslesme.get(key), True)
        durum[key] = {"updated": jira[key].get("_updated_iso", ""),
                      "uat_key": uat_eslesme.get(key, {}).get("uat_key", "")}
        eklenen += 1

    # ── Yazım ──
    damga = datetime.now().strftime("%Y-%m-%d_%H%M")
    taban = re.sub(r"_\d{4}-\d{2}-\d{2}_\d{4}$", "", excel_path.stem)
    cikti_yol = cikti_dir / f"{taban}_{damga}.xlsx"

    if guncellenen == 0 and eklenen == 0:
        shutil.copyfile(excel_path, cikti_yol)      # hiç değişiklik yok → sadece kopyala
    else:
        # Tabloyu yeni son satır/kolonu kapsayacak şekilde genişlet
        yeni_son_satir = max(t_r2, max((r for r, _ in yazimlar), default=t_r2))
        yeni_son_kol = max(t_c2, uat_son_kol)
        tablo_ref = None
        if tablo is not None:
            tablo_ref = (f"{_kolon_harf(t_c1)}{t_r1}:"
                         f"{_kolon_harf(yeni_son_kol)}{yeni_son_satir}")
        _surgical_yaz(excel_path, cikti_yol, KAYNAK_SHEET, yazimlar,
                      tablo_ref=tablo_ref, tablo_yeni_kolonlar=UAT_BASLIKLAR)

    _durum_yaz(state_path, durum)

    return {
        "ok": True,
        "cikti_dosya": cikti_yol.name,
        "guncellenen": guncellenen,
        "eklenen": eklenen,
        "degismeyen": degismeyen,
        "yeni_uat_baglantisi": yeni_uat,
        "uyarilar": uyarilar,
        "sheet": KAYNAK_SHEET,
        "toplam_satir": len(key_satir) + eklenen,
    }
