"""
Kod kaynağı soyutlaması — deterministik test (v2 Faz 3 · 3a). AI/kota YOK.
Geçici git repo oluşturur; konfig'i ona yönlendirir; yol-güvenliğini de sınar.
Çalıştır:  venv/bin/python tests/test_kod_kaynagi.py
"""

import sys
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import skills.kod_kaynagi as kk   # noqa: E402

ok = 0


def dogru(kosul, ad):
    global ok
    assert kosul, f"FAIL {ad}"
    ok += 1
    print(f"  ✓ {ad}")


# Geçici repo
repo = Path(tempfile.mkdtemp()) / "trade"
(repo / "src").mkdir(parents=True)
(repo / "src" / "wallet.py").write_text("def refund(amount):\n    # iade akışı\n    return amount\n", encoding="utf-8")
(repo / "src" / "auth.js").write_text("export function login(user) { return verify2FA(user); }\n", encoding="utf-8")
(repo / "node_modules").mkdir()
(repo / "node_modules" / "junk.js").write_text("SECRET refund\n", encoding="utf-8")
(repo / "README.md").write_text("# Trade\nrefund + login\n", encoding="utf-8")
subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "ilk"], cwd=repo, check=True)

# Konfig'i geçici repoya yönlendir (gerçek reference/ dosyasına dokunma)
kk.konfig_oku = lambda: {"repolar": [{"ad": "trade", "yol": str(repo), "aktif": True}]}

dogru(kk.yapilandirildi_mi(), "yapılandırıldı")
rs = kk.repolar()
dogru(len(rs) == 1 and rs[0]["git"] and rs[0]["branch"], "repo durumu + git + branch")
dogru("Python" in rs[0]["diller"] and "JavaScript" in rs[0]["diller"], "dil tespiti")
dogru(rs[0]["dosya"] >= 3, "dosya sayımı (node_modules hariç)")

t = kk.dosya_agaci("trade", "")
dogru(t["ok"] and any(k["ad"] == "src" for k in t["klasorler"]), "ağaç: src klasörü")
dogru(not any(k["ad"] == "node_modules" for k in t["klasorler"]), "ağaç: node_modules gizli")
ts = kk.dosya_agaci("trade", "src")
dogru(any(f["ad"] == "wallet.py" and f["dil"] == "Python" for f in ts["dosyalar"]), "ağaç: src/wallet.py")

r = kk.dosya_oku("trade", "src/wallet.py")
dogru(r["ok"] and "iade akışı" in r["icerik"] and r["dil"] == "Python", "dosya oku")

# Yol güvenliği: kaçış girişimleri reddedilmeli
dogru(not kk.dosya_oku("trade", "../../etc/passwd")["ok"], "yol kaçışı ../.. reddedildi")
dogru(not kk.dosya_oku("trade", "/etc/passwd")["ok"], "mutlak yol reddedildi")
dogru(kk.dosya_agaci("trade", "../..")["ok"] is False, "ağaç kaçışı reddedildi")

s = kk.ara("trade", "refund")
dogru(s["ok"] and s["adet"] >= 2, "arama: refund bulundu")
dogru(all("node_modules" not in e["yol"] for e in s["eslesmeler"]), "arama: node_modules taranmadı")
dogru(any(e["yol"].endswith("wallet.py") for e in s["eslesmeler"]), "arama: wallet.py eşleşti")
dogru(not kk.ara("trade", "x")["ok"], "arama: <2 karakter reddedildi")

g = kk.git_gecmis("trade", "src/wallet.py")
dogru(g["ok"] and len(g["commits"]) == 1 and g["commits"][0]["mesaj"] == "ilk", "git geçmiş")

# Yapılandırılmamış repo
dogru(not kk.dosya_oku("yok", "x")["ok"], "bilinmeyen repo reddedildi")

print(f"\nKOD KAYNAĞI TESTLERİ GEÇTİ ({ok} kontrol)")
