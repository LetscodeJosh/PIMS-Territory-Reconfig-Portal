#!/usr/bin/env bash
# =============================================================================
# PIMS Territory Reconfiguration Portal - 1-Click Update Script
# Pulls latest changes from GitHub, updates dependencies, and reloads service.
# =============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${APP_DIR}"

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}  Updating PIMS Territory Reconfiguration Portal to Latest Version     ${NC}"
echo -e "${BLUE}======================================================================${NC}"

echo -e "${GREEN}[1/4] Pulling latest commits from git main branch...${NC}"
git pull origin main

echo -e "\n${GREEN}[2/4] Updating Python dependencies...${NC}"
source "${APP_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${APP_DIR}/requirements.txt"

echo -e "\n${GREEN}[3/4] Restarting systemd service...${NC}"
sudo systemctl restart pims-portal.service
sudo systemctl reload nginx

echo -e "\n${GREEN}[4/4] Verifying service status...${NC}"
sleep 2
sudo systemctl status pims-portal.service --no-pager

echo -e "\n${BLUE}======================================================================${NC}"
echo -e "${GREEN}  UPDATE COMPLETED SUCCESSFULLY!${NC}"
echo -e "${BLUE}======================================================================${NC}"
