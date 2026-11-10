#!/usr/bin/env bash
# =============================================================================
# PIMS Territory Reconfiguration Portal - Free Let's Encrypt SSL/HTTPS Setup
# =============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage:${NC} bash setup_ssl.sh <your-domain.com>"
    echo -e "Example: bash setup_ssl.sh territory.pmii-marketing.com"
    exit 1
fi

DOMAIN="$1"

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}  Setting up Free SSL/HTTPS Certificate for: ${DOMAIN}               ${NC}"
echo -e "${BLUE}======================================================================${NC}"

# Install Certbot via APT (Pure Linux packages, no Docker)
sudo apt-get update -y
sudo apt-get install -y certbot python3-certbot-nginx

# Update Nginx Server Name
sudo sed -i "s/server_name _;/server_name ${DOMAIN};/g" /etc/nginx/sites-available/pims-portal
sudo nginx -t
sudo systemctl reload nginx

# Obtain and install SSL certificate automatically
echo -e "\n${GREEN}Requesting Let's Encrypt SSL Certificate...${NC}"
sudo certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --register-unsafely-without-email --redirect

echo -e "\n${BLUE}======================================================================${NC}"
echo -e "${GREEN}  SSL CONFIGURATION COMPLETE!${NC}"
echo -e "  Your portal is now securely accessible via HTTPS:"
echo -e "  🔒 ${YELLOW}https://${DOMAIN}${NC}"
echo -e "${BLUE}======================================================================${NC}"

