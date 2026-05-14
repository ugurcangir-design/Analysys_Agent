#!/bin/bash
set -e

echo "=== BRD Analyst Agent Kurulum ==="

# Python kontrol
if ! command -v python3 &>/dev/null; then
    echo "HATA: python3 bulunamadı."
    exit 1
fi

PYTHON=$(command -v python3)
echo "Python: $PYTHON ($($PYTHON --version))"

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
    echo ">>> .env dosyası oluşturuldu. ANTHROPIC_API_KEY değerini girin."
fi

# start.sh üret
cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python app.py
EOF
chmod +x start.sh

echo ""
echo "=== Kurulum tamamlandı ==="
echo "Başlatmak için: ./start.sh"
