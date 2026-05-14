#!/bin/bash
# BRD Analyst Agent — macOS masaüstü ikonu oluşturucu

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="BRD Analyst Agent"
APP_PATH="$HOME/Desktop/$APP_NAME.app"

echo "=== Masaüstü ikonu oluşturuluyor ==="

# Eski varsa temizle
rm -rf "$APP_PATH"

# Dizin yapısı
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

# ── Info.plist ────────────────────────────────────────────────────────────────
cat > "$APP_PATH/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>launcher</string>
    <key>CFBundleIdentifier</key><string>com.brd-analyst-agent</string>
    <key>CFBundleName</key><string>BRD Analyst Agent</string>
    <key>CFBundleDisplayName</key><string>BRD Analyst Agent</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# ── İkon oluştur (Python stdlib) ──────────────────────────────────────────────
ICON_PY="$APP_PATH/Contents/Resources/_make_icon.py"

cat > "$ICON_PY" << 'PYEOF'
import struct, zlib, os, subprocess, tempfile, shutil, sys

RESOURCES = sys.argv[1]

def png_yaz(yol, w, h, piksel_fn):
    def chunk(ad, veri):
        crc = zlib.crc32(ad + veri) & 0xFFFFFFFF
        return struct.pack('>I', len(veri)) + ad + veri + struct.pack('>I', crc)
    rows = b''
    for y in range(h):
        rows += b'\x00'
        for x in range(w):
            rows += bytes(piksel_fn(x, y))
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(rows, 6))
    iend = chunk(b'IEND', b'')
    with open(yol, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend)

def piksel(x, y, S=512):
    cx, cy = S//2, S//2
    dx, dy = x - cx, y - cy
    # Koyu arka plan
    BG  = (13, 20, 30, 255)
    DOC = (20, 30, 48, 255)
    AC  = (45, 212, 191, 255)
    AC2 = (20, 184, 166, 255)
    # Belge kutusu
    bw, bh = int(S*.66), int(S*.70)
    rx, ry = bw//2, bh//2
    rk = int(S*.09)
    qx = abs(dx) - (rx - rk)
    qy = abs(dy) - (ry - rk)
    if qx > 0 and qy > 0:
        in_box = qx*qx + qy*qy < rk*rk
    else:
        in_box = abs(dx) < rx and abs(dy) < ry
    if not in_box:
        return BG
    # Köşe katlama (sağ üst)
    fold = int(S * .13)
    fx, fy = rx - fold, -ry + fold
    if dx > fx and dy < fy + fold:
        if (dx - fx) + (-dy + fy) > fold:
            return DOC  # katlama arkası
        return AC2      # katlama üçgeni
    # Metin satırları
    sw = int(bw * .54)
    sh = int(S * .024)
    gap = int(S * .063)
    y0 = int(-bh * .09)
    for i in range(4):
        ly = y0 + i * gap
        gw = sw if i < 3 else int(sw * .58)
        if abs(dy - ly) < sh and abs(dx) < gw:
            return AC
    return DOC

SIZE = 512
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'icon.png')
png_yaz(src, SIZE, SIZE, lambda x,y: piksel(x,y,SIZE))

iconset = os.path.join(tmp, 'AppIcon.iconset')
os.makedirs(iconset)
specs = [
    ('icon_16x16.png',      16),
    ('icon_16x16@2x.png',   32),
    ('icon_32x32.png',      32),
    ('icon_32x32@2x.png',   64),
    ('icon_128x128.png',   128),
    ('icon_128x128@2x.png',256),
    ('icon_256x256.png',   256),
    ('icon_256x256@2x.png',512),
    ('icon_512x512.png',   512),
]
for name, size in specs:
    dst = os.path.join(iconset, name)
    subprocess.run(['sips', '-z', str(size), str(size), src, '--out', dst],
                   capture_output=True, check=False)

icns = os.path.join(RESOURCES, 'AppIcon.icns')
result = subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', icns],
                        capture_output=True, check=False)
shutil.rmtree(tmp)

if os.path.exists(icns):
    print(f'✓ İkon oluşturuldu: {icns}')
else:
    print(f'⚠ İkon oluşturulamadı: {result.stderr.decode()}', file=sys.stderr)
PYEOF

python3 "$ICON_PY" "$APP_PATH/Contents/Resources"
rm "$ICON_PY"

# ── Launcher ──────────────────────────────────────────────────────────────────
LAUNCHER="$APP_PATH/Contents/MacOS/launcher"

cat > "$LAUNCHER" << LAUNCHEOF
#!/bin/bash
PROJECT="$PROJECT_DIR"
PORT=5002
URL="http://localhost:\$PORT"

# Zaten çalışıyorsa sadece tarayıcı aç
if curl -s --max-time 1 "\$URL" > /dev/null 2>&1; then
    open "\$URL"
    exit 0
fi

# Server başlat (desktop modu)
cd "\$PROJECT"
source venv/bin/activate
DESKTOP_MODE=true python app.py > /tmp/brd-agent-desktop.log 2>&1 &
SERVER_PID=\$!

# Hazır olana kadar bekle (max 15 saniye)
for i in \$(seq 1 30); do
    sleep 0.5
    curl -s --max-time 1 "\$URL" > /dev/null 2>&1 && break
done

# Tarayıcıyı aç
open "\$URL"

# Server kapanana kadar bekle
wait \$SERVER_PID
LAUNCHEOF

chmod +x "$LAUNCHER"

# macOS'a ikonu tanıt
touch "$APP_PATH"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$APP_PATH" 2>/dev/null || true

echo "✓ Masaüstü ikonu hazır: $APP_PATH"
echo "  Çift tıklayarak uygulamayı başlatabilirsiniz."
