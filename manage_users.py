#!/usr/bin/env python3
"""
Kullanıcı yönetimi — ilk kurulum ve terminal üzerinden kullanıcı ekleme/silme.

Kullanım:
  python manage_users.py ekle <kullanici_adi> <sifre>
  python manage_users.py sil <kullanici_adi>
  python manage_users.py listele
  python manage_users.py sifre <kullanici_adi> <yeni_sifre>
"""

import sys
import json
from pathlib import Path
from werkzeug.security import generate_password_hash

USERS_PATH = Path(__file__).parent / "users.json"


def oku():
    if not USERS_PATH.exists():
        return {}
    return json.loads(USERS_PATH.read_text(encoding="utf-8"))


def yaz(users):
    USERS_PATH.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def ekle(username, password):
    if len(username) < 2:
        print("HATA: Kullanıcı adı en az 2 karakter olmalı."); sys.exit(1)
    if len(password) < 6:
        print("HATA: Şifre en az 6 karakter olmalı."); sys.exit(1)
    users = oku()
    if username in users:
        print(f"HATA: '{username}' zaten mevcut."); sys.exit(1)
    users[username] = generate_password_hash(password)
    yaz(users)
    print(f"✓ Kullanıcı eklendi: {username}")


def sil(username):
    users = oku()
    if username not in users:
        print(f"HATA: '{username}' bulunamadı."); sys.exit(1)
    del users[username]
    yaz(users)
    print(f"✓ Kullanıcı silindi: {username}")


def listele():
    users = oku()
    if not users:
        print("Henüz kullanıcı yok.")
        return
    print(f"Toplam {len(users)} kullanıcı:")
    for u in users:
        print(f"  • {u}")


def sifre_degistir(username, yeni_sifre):
    if len(yeni_sifre) < 6:
        print("HATA: Şifre en az 6 karakter olmalı."); sys.exit(1)
    users = oku()
    if username not in users:
        print(f"HATA: '{username}' bulunamadı."); sys.exit(1)
    users[username] = generate_password_hash(yeni_sifre)
    yaz(users)
    print(f"✓ Şifre güncellendi: {username}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)

    cmd = args[0]
    if cmd == "ekle" and len(args) == 3:
        ekle(args[1], args[2])
    elif cmd == "sil" and len(args) == 2:
        sil(args[1])
    elif cmd == "listele":
        listele()
    elif cmd == "sifre" and len(args) == 3:
        sifre_degistir(args[1], args[2])
    else:
        print(__doc__); sys.exit(1)
