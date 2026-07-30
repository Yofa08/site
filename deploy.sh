#!/bin/bash
# ── Deal Manager — Quick Deploy Script ─────────────────────
# Usage: bash deploy.sh
# Deploys to /opt/deal-manager with systemd + nginx.

set -e

APP_DIR="/opt/deal-manager"
VENV_DIR="$APP_DIR/.venv"
SERVICE_NAME="deal-manager"

echo "=== Deal Manager Deploy ==="
echo ""

# 1. Install system packages
echo "[1/6] Installing system dependencies..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-venv python3-pip nginx
elif command -v yum &>/dev/null; then
    sudo yum install -y python3 python3-pip nginx
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3 python3-pip nginx
else
    echo "WARNING: Unknown package manager. Install python3 and nginx manually."
fi

# 2. Copy files
echo "[2/6] Copying files to $APP_DIR..."
sudo mkdir -p "$APP_DIR"
sudo cp -r ./* "$APP_DIR/"
sudo chown -R www-data:www-data "$APP_DIR" 2>/dev/null || sudo chown -R $USER:$USER "$APP_DIR"

# 3. Python venv + deps
echo "[3/6] Setting up Python environment..."
cd "$APP_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q -r requirements.txt

# 4. Create .env if not exists
echo "[4/6] Configuring environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "  Created .env from .env.example — edit it now:"
    echo "    sudo nano $APP_DIR/.env"
fi

# 5. Install systemd service
echo "[5/6] Installing systemd service..."
if ! id -u www-data &>/dev/null; then
    sudo useradd -r -s /bin/false www-data 2>/dev/null || true
fi
sudo cp "$APP_DIR/deal-manager.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
echo "  Service status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -6

# 6. Nginx
echo "[6/6] Configuring nginx..."
if [ -f "$APP_DIR/nginx.conf" ]; then
    sudo cp "$APP_DIR/nginx.conf" /etc/nginx/sites-available/deal-manager
    sudo ln -sf /etc/nginx/sites-available/deal-manager /etc/nginx/sites-enabled/ 2>/dev/null || true
    # Remove default if it exists
    sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    sudo nginx -t && sudo systemctl reload nginx
    echo "  Nginx configured. Edit domain:"
    echo "    sudo nano /etc/nginx/sites-available/deal-manager"
fi

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "  Admin:     http://your-server:8000/admin"
echo "  Public:    http://your-server:8000/"
echo "  Settings:  http://your-server:8000/admin/settings"
echo ""
echo "  Service:   sudo systemctl restart deal-manager"
echo "  Logs:      sudo journalctl -u deal-manager -f"
