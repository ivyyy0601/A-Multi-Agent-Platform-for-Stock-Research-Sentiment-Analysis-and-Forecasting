#!/bin/bash
# IvyTrader Server Setup Script
# Run this once on a fresh Ubuntu 22.04 server as root.
# Usage: bash server_setup.sh

set -e
APP_DIR="/opt/ivytrader"

echo "=== [1/7] Installing system packages ==="
apt-get update -q
apt-get install -y software-properties-common curl nginx nodejs npm
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -q
apt-get install -y python3 python3-pip python3-venv python3.11 python3.11-venv python3.11-dev

echo "=== [2/7] Setting up main backend (port 8000) ==="
cd "$APP_DIR"
python3.11 -m venv .venv311
.venv311/bin/python -m pip install --upgrade pip -q
.venv311/bin/python -m pip install -r requirements.txt -q

echo "=== [3/7] Setting up analysis backend (port 8001) ==="
cd "$APP_DIR/backend_analysis"
python3 -m venv venv
venv/bin/python -m pip install --upgrade pip -q
venv/bin/python -m pip install -r requirements.txt -q

echo "=== [4/7] Building frontend ==="
cd "$APP_DIR/frontend"
npm install -q
npm run build
# Copy built files to nginx web root
mkdir -p /var/www/ivytrader
cp -r dist/* /var/www/ivytrader/

echo "=== [5/7] Creating systemd services ==="

# Main backend service
cat > /etc/systemd/system/ivytrader-main.service << 'SERVICE'
[Unit]
Description=IvyTrader Main Backend
After=network.target

[Service]
WorkingDirectory=/opt/ivytrader
EnvironmentFile=/opt/ivytrader/.env
Environment=DATABASE_PATH=/opt/ivytrader/pokieticker.db
ExecStart=/opt/ivytrader/.venv311/bin/python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SERVICE

# Analysis backend service
cat > /etc/systemd/system/ivytrader-analysis.service << 'SERVICE'
[Unit]
Description=IvyTrader Analysis Backend
After=network.target

[Service]
WorkingDirectory=/opt/ivytrader/backend_analysis
EnvironmentFile=/opt/ivytrader/backend_analysis/.env
ExecStart=/opt/ivytrader/backend_analysis/venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ivytrader-main ivytrader-analysis
systemctl start ivytrader-main ivytrader-analysis

echo "=== [6/7] Setting up nginx ==="
cat > /etc/nginx/sites-available/ivytrader << 'NGINX'
server {
    listen 80;
    server_name _;

    # Frontend (built static files)
    location / {
        root /var/www/ivytrader;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Analysis backend API
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Main backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/ivytrader /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "=== [7/7] Setting up cron jobs ==="
crontab - << 'CRON'
SHELL=/bin/bash
CRON_TZ=America/New_York

# IvyTrader nightly automation
# 6:00 PM ET — fetch, submit, collect, retrain, cache forecasts
0 18 * * * cd /opt/ivytrader && /bin/bash /opt/ivytrader/nightly_pipeline.sh
CRON

echo ""
echo "============================================"
echo "  Setup complete!"
echo "  Open http://$(curl -s ifconfig.me) in your browser"
echo "============================================"
echo ""
echo "Check service status:"
echo "  systemctl status ivytrader-main"
echo "  systemctl status ivytrader-analysis"
echo ""
echo "Check logs:"
echo "  tail -f /opt/ivytrader/logs/nightly_*.log"
