#!/bin/bash
# BRD Analyst Agent — macOS masaüstü ikonu oluşturucu
# AppleScript tabanlı — macOS'ta güvenilir çalışır

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="BRD Analyst Agent"
APP_PATH="$HOME/Desktop/$APP_NAME.app"

echo "=== Masaüstü ikonu oluşturuluyor ==="

# ── Yardımcı başlatıcı ────────────────────────────────────────────────────────
# (AppleScript içinden çağrılır; do shell script bloke etmez çünkü & ile background)
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

# ── AppleScript app oluştur ───────────────────────────────────────────────────
rm -rf "$APP_PATH"

osacompile -o "$APP_PATH" -e "
on run
    try
        do shell script \"$HELPER\"
    on error
    end try
end run
"

# ── plist güncelle ────────────────────────────────────────────────────────────
PLIST="$APP_PATH/Contents/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleName 'BRD Analyst Agent'"         "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'BRD Analyst Agent'"  "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier 'com.brd-analyst-agent'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true"                     "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSUIElement true"                          "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true"         "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :NSHighResolutionCapable true"              "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon"                  "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon"           "$PLIST" 2>/dev/null || true

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
    cx, cy = S//2, S//2
    dx, dy = x - cx, y - cy
    BG  = (13, 20, 30, 255)
    DOC = (20, 30, 48, 255)
    AC  = (45, 212, 191, 255)
    AC2 = (20, 184, 166, 255)
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
    fold = int(S * .13)
    fx, fy = rx - fold, -ry + fold
    if dx > fx and dy < fy + fold:
        if (dx - fx) + (-dy + fy) > fold:
            return DOC
        return AC2
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

# osacompile'ın eklediği default ikonları kaldır, bizimkini bırak
rm -f "$APP_PATH/Contents/Resources/applet.icns" 2>/dev/null || true

# ── macOS kayıt + quarantine ──────────────────────────────────────────────────
touch "$APP_PATH"
xattr -rd com.apple.quarantine "$APP_PATH" 2>/dev/null || true
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$APP_PATH" 2>/dev/null || true

echo "✓ Masaüstü ikonu hazır: $APP_PATH"
echo "  Çift tıklayarak uygulamayı başlatabilirsiniz."
