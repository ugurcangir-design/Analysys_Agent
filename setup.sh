#!/bin/bash
set -e

echo "=== Analyst Studio Kurulum ==="

# Python kontrol — 3.10+ zorunlu (kod 'str | None' union tipleri kullanır)
if ! command -v python3 &>/dev/null; then
    echo "HATA: python3 bulunamadı. Python 3.10 veya üzeri kurun."
    exit 1
fi

PYTHON=$(command -v python3)
PY_VER=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python: $PYTHON ($($PYTHON --version))"

# Sürüm 3.10+ mı kontrol et
$PYTHON -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "HATA: Python 3.10 veya üzeri gerekli (mevcut: $PY_VER)."
    echo "      Kod modern tip ifadeleri ('str | None') kullanır."
    echo "      brew install python@3.12  ile güncelleyebilirsiniz."
    exit 1
}

# venv oluştur
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "venv oluşturuldu."
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "Paketler yüklendi."

# .env kontrol
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo ">>> .env dosyası oluşturuldu."
    echo "    VARSAYILAN: Claude CLI modu (USE_CLAUDE_CLI=true) — abonelik kapsamında, ücretsiz."
    echo "    Claude CLI kurulu değilse:  npm install -g @anthropic-ai/claude-code"
    echo "    Alternatif (API modu): .env içinde ANTHROPIC_API_KEY tanımlayın."
fi

# start.sh üret (terminal'den başlatmak için)
cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python app.py
EOF
chmod +x start.sh

echo ""
echo "=== Masaüstü ikonu oluşturuluyor ==="
bash create_app.sh

echo ""
echo "=== Kurulum tamamlandı ==="
echo "Masaüstündeki 'Analyst Studio' uygulamasına çift tıklayarak başlatabilirsiniz."
echo "Alternatif: ./start.sh ile terminalden çalıştırın → http://localhost:5002"
