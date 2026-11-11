#!/usr/bin/env bash
# =============================================================================
# PIMS Territory Reconfiguration Portal - GCP Automated Bare-Metal Installer
# Pure Linux VM Deployment (Zero Docker / Zero Container Extensions)
# Compatible with Ubuntu 20.04 / 22.04 / 24.04 LTS & Debian 11 / 12
# =============================================================================

set -e

# ANSI Color Codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}  PIMS Territory Reconfiguration Portal - GCP Turnkey Bare-Metal Setup  ${NC}"
echo -e "${BLUE}======================================================================${NC}"

# 1. Resolve Execution Context
CURRENT_USER=$(whoami)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${APP_DIR}/venv"

echo -e "${GREEN}[1/7] Detected deployment context:${NC}"
echo -e "      User:           ${YELLOW}${CURRENT_USER}${NC}"
echo -e "      App Directory:  ${YELLOW}${APP_DIR}${NC}"
echo -e "      Virtualenv:     ${YELLOW}${VENV_DIR}${NC}"

# 2. Check Sudo Privileges
if [ "$EUID" -ne 0 ] && ! sudo -n true 2>/dev/null; then
    echo -e "${YELLOW}[!] Sudo authentication required for package and service installation.${NC}"
    sudo true
fi

# 3. Install System Dependencies via APT (Pure Linux packages, no Docker)
echo -e "\n${GREEN}[2/7] Installing pure system packages via APT...${NC}"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    git \
    nginx \
    curl \
    ca-certificates

# 4. Set Up Python Virtual Environment
echo -e "\n${GREEN}[3/7] Setting up Python virtual environment...${NC}"
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi

# Activate venv & install Python dependencies
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip setuptools wheel
pip install -r "${APP_DIR}/requirements.txt"

# 5. Configure Systemd Background Service
echo -e "\n${GREEN}[4/7] Configuring systemd background service (pims-portal.service)...${NC}"
SERVICE_FILE="/etc/systemd/system/pims-portal.service"

sudo bash -c "cat << 'EOF' > ${SERVICE_FILE}
[Unit]
Description=PIMS Territory Reconfiguration Portal (Pure GCP Bare-Metal Streamlit Service)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
Restart=always
RestartSec=5s

Environment=PYTHONUNBUFFERED=1
Environment=LC_ALL=C.UTF-8
Environment=LANG=C.UTF-8

NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=${APP_DIR}

LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable pims-portal.service
sudo systemctl restart pims-portal.service

# Configure passwordless systemctl permissions for automated GitHub Actions CI/CD
echo "${CURRENT_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart pims-portal.service, /bin/systemctl reload pims-portal.service, /bin/systemctl status pims-portal.service" | sudo tee /etc/sudoers.d/pims-portal-cicd > /dev/null
sudo chmod 0440 /etc/sudoers.d/pims-portal-cicd

# 6. Configure Nginx Reverse Proxy
echo -e "\n${GREEN}[5/7] Configuring Nginx reverse proxy on Port 80...${NC}"
NGINX_CONF="/etc/nginx/sites-available/pims-portal"

sudo cp "${APP_DIR}/deploy/gcp/nginx-pims.conf" "${NGINX_CONF}"

# Enable site
if [ ! -f "/etc/nginx/sites-enabled/pims-portal" ]; then
    sudo ln -s "${NGINX_CONF}" /etc/nginx/sites-enabled/pims-portal
fi

# Remove default nginx welcome page if active
if [ -f "/etc/nginx/sites-enabled/default" ]; then
    sudo rm -f /etc/nginx/sites-enabled/default
fi

# Test Nginx syntax and reload
sudo nginx -t
sudo systemctl reload nginx

# 7. Local Firewall Adjustment (if ufw is active)
if command -v ufw &> /dev/null; then
    if sudo ufw status | grep -q "Status: active"; then
        echo -e "\n${GREEN}[6/7] Allowing HTTP/HTTPS traffic through UFW...${NC}"
        sudo ufw allow 'Nginx Full' || sudo ufw allow 80/tcp
    fi
fi

# 8. Health Verification
echo -e "\n${GREEN}[7/7] Verifying service health...${NC}"
sleep 3

MAX_RETRIES=10
RETRY_COUNT=0
HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://127.0.0.1:8501/_stcore/health | grep -q "ok"; then
        HEALTHY=true
        break
    fi
    sleep 2
    RETRY_COUNT=$((RETRY_COUNT+1))
done

# Resolve External IP
EXT_IP=$(curl -s -m 3 -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null || curl -s -m 3 https://ifconfig.me 2>/dev/null || echo "<YOUR_GCP_VM_EXTERNAL_IP>")

echo -e "\n${BLUE}======================================================================${NC}"
if [ "$HEALTHY" = true ]; then
    echo -e "${GREEN}  DEPLOYMENT SUCCESSFUL! PIMS Territory Portal is LIVE!${NC}"
    echo -e "${BLUE}======================================================================${NC}"
    echo -e "Access the web portal directly in your browser:"
    echo -e "  🌐 URL: ${YELLOW}http://${EXT_IP}${NC}"
    echo -e "\nService Status Check:"
    echo -e "  Command: ${YELLOW}sudo systemctl status pims-portal${NC}"
    echo -e "View Live Logs:"
    echo -e "  Command: ${YELLOW}sudo journalctl -u pims-portal -f${NC}"
else
    echo -e "${YELLOW}[!] Service started. It may take another few seconds to initialize.${NC}"
    echo -e "Check status: ${YELLOW}sudo systemctl status pims-portal${NC}"
    echo -e "Check logs:   ${YELLOW}sudo journalctl -u pims-portal -f${NC}"
fi
echo -e "${BLUE}======================================================================${NC}"

