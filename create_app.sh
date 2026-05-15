#!/bin/bash
# Analyst Studio — macOS masaüstü ikonu oluşturucu
# Swift binary tabanlı — macOS 26+ Finder ile uyumlu

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Analyst Studio"
APP_PATH="$HOME/Desktop/$APP_NAME.app"

echo "=== Masaüstü ikonu oluşturuluyor ==="

# ── Yardımcı başlatıcı ────────────────────────────────────────────────────────
HELPER="$PROJECT_DIR/_start.sh"
cat > "$HELPER" << SHEOF
#!/bin/bash
PORT=5002
URL="http://localhost:\$PORT"
cd "$PROJECT_DIR"

if curl -s --max-time 1 "\$URL" > /dev/null 2>&1; then
    open "\$URL"
    exit 0
fi

source venv/bin/activate
DESKTOP_MODE=true nohup python app.py >> /tmp/brd-agent-desktop.log 2>&1 &
disown

for i in \$(seq 1 30); do
    sleep 0.5
    curl -s --max-time 1 "\$URL" > /dev/null 2>&1 && break
done
open "\$URL"
SHEOF
chmod +x "$HELPER"

# ── Swift launcher binary oluştur ─────────────────────────────────────────────
SWIFT_SRC=$(mktemp /tmp/brd_launcher_XXXX.swift)

cat > "$SWIFT_SRC" << SWIFTEOF
import Foundation

let task = Process()
task.executableURL = URL(fileURLWithPath: "/bin/bash")
task.arguments = ["$HELPER"]
task.standardInput = FileHandle.nullDevice
task.standardOutput = FileHandle.nullDevice
task.standardError = FileHandle.nullDevice
try? task.run()

Thread.sleep(forTimeInterval: 0.5)
exit(0)
SWIFTEOF

BINARY_PATH="$PROJECT_DIR/_launcher_bin"
echo "  Swift derleniyor..."
swiftc "$SWIFT_SRC" -o "$BINARY_PATH" 2>/dev/null
rm "$SWIFT_SRC"
echo "  ✓ Launcher derlendi"

# ── App bundle oluştur ────────────────────────────────────────────────────────
rm -rf "$APP_PATH"
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

# Binary'yi bundle'a kopyala
cp "$BINARY_PATH" "$APP_PATH/Contents/MacOS/BRDAnalystAgent"
chmod +x "$APP_PATH/Contents/MacOS/BRDAnalystAgent"

# ── Info.plist ────────────────────────────────────────────────────────────────
cat > "$APP_PATH/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Analyst Studio</string>
    <key>CFBundleDisplayName</key>
    <string>Analyst Studio</string>
    <key>CFBundleIdentifier</key>
    <string>com.analyst-studio</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>BRDAnalystAgent</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
</dict>
</plist>
PLIST

# ── İkon oluştur ──────────────────────────────────────────────────────────────
ICON_PY=$(mktemp /tmp/make_icon_XXXX.py)

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
    BG   = (13,  20,  30,  255)   # koyu lacivert zemin
    AC   = (45,  212, 191, 255)   # ana teal
    AC2  = (20,  184, 166, 255)   # koyu teal (çubuk alt)
    AC3  = (167, 243, 232, 255)   # açık teal (veri noktası / trend)
    GRID = (22,  33,  48,  255)   # ızgara çizgisi rengi

    # ── Yuvarlak köşeli kare arka plan ────────────────────────────
    pad = int(S * .08)
    rk  = int(S * .18)
    cx, cy = S // 2, S // 2
    ax, ay = abs(x - cx), abs(y - cy)
    lim = S // 2 - pad
    qx, qy = ax - (lim - rk), ay - (lim - rk)
    if qx > 0 and qy > 0:
        if qx * qx + qy * qy > rk * rk:
            return BG
    elif ax > lim or ay > lim:
        return BG

    # ── Yatay ızgara çizgileri (3 adet, soluk) ────────────────────
    base_y = int(S * .75)
    for gi in range(1, 4):
        gy = base_y - int(S * .18 * gi)
        if abs(y - gy) <= 1:
            return GRID

    # ── Çubuklar (4 adet, yükselen) ───────────────────────────────
    n      = 4
    bw     = int(S * .105)
    bgap   = int(S * .048)
    total  = n * bw + (n - 1) * bgap
    ox     = (S - total) // 2
    heights = [int(S * h) for h in (.20, .34, .50, .62)]
    br     = int(bw * .35)   # üst köşe yarıçapı

    for i in range(n):
        x0, x1 = ox + i * (bw + bgap), ox + i * (bw + bgap) + bw
        y0, y1 = base_y - heights[i], base_y
        if x0 <= x < x1 and y0 <= y <= y1:
            in_bar = True
            if x - x0 < br and y - y0 < br:
                ddx, ddy = x - (x0 + br), y - (y0 + br)
                if ddx * ddx + ddy * ddy > br * br:
                    in_bar = False
            elif x1 - x <= br and y - y0 < br:
                ddx, ddy = x - (x1 - br), y - (y0 + br)
                if ddx * ddx + ddy * ddy > br * br:
                    in_bar = False
            if in_bar:
                t  = (y - y0) / max(heights[i], 1)
                r  = int(AC[0] + t * (AC2[0] - AC[0]))
                g  = int(AC[1] + t * (AC2[1] - AC[1]))
                b  = int(AC[2] + t * (AC2[2] - AC[2]))
                return (r, g, b, 255)

    # ── Veri noktaları (çubuk tepeleri) ───────────────────────────
    pts = [(ox + i * (bw + bgap) + bw // 2, base_y - heights[i]) for i in range(n)]
    dr  = int(S * .030)
    for px, py in pts:
        if (x - px) ** 2 + (y - py) ** 2 <= dr * dr:
            return AC3

    # ── Trend çizgisi ─────────────────────────────────────────────
    lw2 = 2.8 ** 2   # çizgi yarı genişliği²
    for i in range(len(pts) - 1):
        x1p, y1p = pts[i];  x2p, y2p = pts[i + 1]
        ddx, ddy = x2p - x1p, y2p - y1p
        L2 = ddx * ddx + ddy * ddy
        if L2 == 0:
            continue
        t = ((x - x1p) * ddx + (y - y1p) * ddy) / L2
        t = max(0.0, min(1.0, t))
        cx2 = x1p + t * ddx;  cy2 = y1p + t * ddy
        dist2 = (x - cx2) ** 2 + (y - cy2) ** 2
        if dist2 <= lw2:
            return AC3

    return (13, 20, 30, 255)

SIZE = 512
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'icon.png')
png_yaz(src, SIZE, SIZE, lambda x, y: piksel(x, y, SIZE))

iconset = os.path.join(tmp, 'AppIcon.iconset')
os.makedirs(iconset)
specs = [
    ('icon_16x16.png',      16),  ('icon_16x16@2x.png',   32),
    ('icon_32x32.png',      32),  ('icon_32x32@2x.png',   64),
    ('icon_128x128.png',   128),  ('icon_128x128@2x.png', 256),
    ('icon_256x256.png',   256),  ('icon_256x256@2x.png', 512),
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

# ── Ad-hoc codesign ───────────────────────────────────────────────────────────
echo "  Codesign uygulanıyor..."
# Önce extended attributes temizle
find "$APP_PATH" -name "._*" -delete 2>/dev/null || true
xattr -rc "$APP_PATH" 2>/dev/null || true

# Binary'yi imzala
codesign --force --sign - \
    --entitlements /dev/null \
    "$APP_PATH/Contents/MacOS/BRDAnalystAgent" 2>/dev/null || true

# Bundle'ı imzala
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || true
echo "  ✓ Codesign tamamlandı"

# ── macOS kayıt ───────────────────────────────────────────────────────────────
xattr -rd com.apple.quarantine "$APP_PATH" 2>/dev/null || true
touch "$APP_PATH"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$APP_PATH" 2>/dev/null || true

echo ""
echo "✓ Masaüstü ikonu hazır: $APP_PATH"
echo "  Çift tıklayarak uygulamayı başlatabilirsiniz."
