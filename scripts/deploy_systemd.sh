#!/usr/bin/env bash
# Usage: sudo ./scripts/deploy_systemd.sh <user> <path-to-repo>
# Example: sudo ./scripts/deploy_systemd.sh ubuntu /home/ubuntu/crypto-bot

USER="$1"
REPO_PATH="$2"
SERVICE_NAME="crypto-bot.service"

cat > /etc/systemd/system/$SERVICE_NAME <<EOF
[Unit]
Description=Crypto Bot Service
After=network.target

[Service]
User=$USER
WorkingDirectory=$REPO_PATH
Environment=PYTHONUNBUFFERED=1
ExecStart=$REPO_PATH/.venv/bin/python -m src.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME
echo "Service deployed: $SERVICE_NAME"
