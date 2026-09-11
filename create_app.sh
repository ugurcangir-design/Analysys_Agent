#!/bin/bash
# Analyst Studio — macOS masaüstü ikonu oluşturucu
# Swift binary tabanlı — macOS 26+ Finder ile uyumlu

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
# v2: eski app (Analyst Studio, 5002) ile çakışmasın diye ayrı isim + port.
# APP_NAME env ile override edilebilir; PORT .env'den türetilir (yoksa 5003).
APP_NAME="${APP_NAME:-Analyst Studio v2}"
APP_PATH="$HOME/Desktop/$APP_NAME.app"
APP_PORT="${PORT:-$(grep -E '^PORT=' "$PROJECT_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"'"'"' ')}"
APP_PORT="${APP_PORT:-5003}"
echo "  Uygulama: $APP_NAME · port $APP_PORT · $PROJECT_DIR"

echo "=== Masaüstü ikonu oluşturuluyor ==="

# ── Yardımcı başlatıcı ────────────────────────────────────────────────────────
HELPER="$PROJECT_DIR/_start.sh"
cat > "$HELPER" << SHEOF
#!/bin/bash
PORT=$APP_PORT
URL="http://localhost:\$PORT"
cd "$PROJECT_DIR"

# macOS GUI uygulamaları minimal PATH alır (/usr/bin:/bin:...) — terminal'in
# nvm / ~/.local/bin / homebrew PATH'i gelmez. claude CLI ve diğer araçların
# bulunabilmesi için yaygın bin dizinlerini + en yeni nvm node'u PATH'e ekle.
export PATH="\$HOME/.local/bin:\$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:\$PATH"
_NVM_BIN=\$(ls -d "\$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)
[ -n "\$_NVM_BIN" ] && export PATH="\$_NVM_BIN:\$PATH"

if curl -s --max-time 1 "\$URL" > /dev/null 2>&1; then
    open "\$URL"
    exit 0
fi

source venv/bin/activate
export PORT   # app.py PORT'u env'den okur — helper'ın portuyla eşleşmeli (yoksa 5002'ye düşer)
DESKTOP_MODE=true nohup python app.py >> /tmp/brd-agent-desktop-v2.log 2>&1 &
disown

for i in \$(seq 1 30); do
    sleep 0.5
    curl -s --max-time 1 "\$URL" > /dev/null 2>&1 && break
done
open "\$URL"
SHEOF
chmod +x "$HELPER"

# ── Swift kontrolü ────────────────────────────────────────────────────────────
# swiftc yoksa (Xcode Command Line Tools kurulu değilse) masaüstü ikonu
# oluşturulamaz — ama uygulama yine de ./start.sh ile çalışır. Kurulumu
# çökertmek yerine zarifçe atla.
if ! command -v swiftc &>/dev/null; then
    echo ""
    echo "  ⚠ swiftc bulunamadı — masaüstü ikonu OLUŞTURULAMADI (kurulum yine de tamam)."
    echo "    Uygulamayı şununla başlatın:  ./start.sh"
    echo "    Masaüstü ikonu isterseniz önce:  xcode-select --install"
    echo "    ardından tekrar:  bash create_app.sh"
    exit 0
fi

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
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.analyst-studio.v2</string>
    <key>CFBundleVersion</key>
    <string>2.1</string>
    <key>CFBundleShortVersionString</key>
    <string>2.1</string>
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
    # Marka ile tutarlı ikon: teal gradient yuvarlak kare + beyaz "analiz çizgileri"
    # (uygulama sol üst brand-mark ile aynı dil). v2.1.
    AC  = (45, 212, 191)     # ana teal
    AC2 = (13, 148, 136)     # koyu teal
    pad = int(S * .06)
    rk  = int(S * .22)
    cx, cy = S // 2, S // 2
    ax, ay = abs(x - cx), abs(y - cy)
    lim = S // 2 - pad
    # Yuvarlak kare DIŞI → şeffaf (macOS ikon köşeleri)
    qx, qy = ax - (lim - rk), ay - (lim - rk)
    if qx > 0 and qy > 0:
        if qx * qx + qy * qy > rk * rk:
            return (0, 0, 0, 0)
    elif ax > lim or ay > lim:
        return (0, 0, 0, 0)
    # Diyagonal (135°) teal gradient zemin
    t = max(0.0, min(1.0, ((x - pad) + (y - pad)) / (2.0 * (S - 2 * pad))))
    bg = (int(AC[0] + t * (AC2[0] - AC[0])),
          int(AC[1] + t * (AC2[1] - AC[1])),
          int(AC[2] + t * (AC2[2] - AC[2])), 255)
    # Beyaz analiz çizgileri (3 yatay, sonuncusu kısa) — yuvarlak uçlu
    lx = int(S * .30)
    lh = int(S * .056)
    lr = lh // 2
    satirlar = [(.365, .40), (.50, .40), (.635, .24)]
    for cyr, lenr in satirlar:
        ly = int(S * cyr)
        x0, x1 = lx, lx + int(S * lenr)
        if abs(y - ly) <= lr:
            if x0 + lr <= x <= x1 - lr:
                return (255, 255, 255, 255)
            for ex in (x0 + lr, x1 - lr):
                if (x - ex) ** 2 + (y - ly) ** 2 <= lr * lr:
                    return (255, 255, 255, 255)
    return bg

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
