# Google Cloud Platform (GCP) Compute Engine Deployment Guide
## PIMS Territory Reconfiguration Portal • Bare-Metal Linux Architecture

This deployment guide provides a **pure bare-metal Linux installation on Google Cloud Platform (GCP) Compute Engine**.
It strictly requires **ZERO Docker, ZERO container runtimes, and ZERO proprietary extensions**.

All configuration is managed directly via **PuTTY** using standard Linux utilities (`apt`, `python3-venv`, `systemd`, `nginx`).

---

## 🏛️ System Architecture Overview

```
[ User Browser / SFE Device ]
              │
              │  HTTP (Port 80) / HTTPS (Port 443)
              ▼
   [ GCP VPC Firewall ] (Allows Port 80 & 443)
              │
              ▼
    [ Nginx Reverse Proxy ] (Caches static files, terminates SSL, proxies WebSockets)
              │
              │  Internal loopback: 127.0.0.1:8501
              ▼
  [ Streamlit Core Application ] (Managed 24/7 by systemd: pims-portal.service)
              │
              │  Frappe REST API (HTTPS)
              ▼
  [ ERPNext v15 Production Backend ]
```

### Key Production Benefits:
* **Zero Container Overhead**: Runs natively on standard Ubuntu or Debian Linux.
* **24/7 Production Resilience**: Managed by `systemd` with automatic restart on reboot and failure recovery.
* **High-Performance Nginx Proxy**: Handles Streamlit WebSockets, Gzip compression (reducing payload from 1.5MB to ~280KB), and security headers.
* **Protected Port Binding**: Streamlit binds strictly to `127.0.0.1:8501` behind Nginx, preventing direct unauthorized access.

---

## 📋 Prerequisites Checklist in GCP Console

Before connecting with PuTTY, ensure your GCP VM has firewall access:

1. **GCP VM Instance**:
   * **Machine Type**: `e2-micro` (Free tier eligible), `e2-small`, or `e2-medium`.
   * **Operating System**: Ubuntu 22.04 LTS (recommended) or Debian 11/12.
   * **Boot Disk**: Standard Persistent Disk (10 GB to 20 GB).
2. **GCP Firewall Rules**:
   * In the GCP Console, go to **Compute Engine** $\rightarrow$ **VM instances**.
   * Click on your VM instance $\rightarrow$ Click **Edit**.
   * Under **Firewall**, check both:
     - ☑ **Allow HTTP traffic** (Port 80)
     - ☑ **Allow HTTPS traffic** (Port 443)
   * Click **Save**.
3. **External Static IP (Recommended)**:
   * Under **VPC network** $\rightarrow$ **IP addresses**, promote your VM's ephemeral External IP to a **Static IP** so the web address never changes after a reboot.

---

## 🚀 Quick Deployment: 1-Command Automated Turnkey Setup

Once you connect to your GCP VM via **PuTTY**, run this single command sequence:

```bash
# 1. Clone the repository into your home directory
git clone https://github.com/LetscodeJosh/PIMS-Territory-Reconfig-Portal.git ~/pims-portal

# 2. Enter directory and run the automated bare-metal installer
cd ~/pims-portal
bash deploy/gcp/install.sh
```

The installer will automatically:
1. Update system packages and install `python3`, `python3-venv`, `git`, and `nginx`.
2. Create an isolated Python virtual environment (`~/pims-portal/venv`).
3. Install required Python packages (`streamlit>=1.35.0`).
4. Generate and enable the `pims-portal.service` `systemd` background service.
5. Configure Nginx with WebSocket support and start the reverse proxy.
6. Print your public web address (e.g. `http://34.x.x.x`).

---

## 🛠️ Alternative: Step-by-Step Manual Deployment via PuTTY

If you prefer full transparency and manual control, execute the following steps in PuTTY:

### Step 1: Update Packages & Install Pure Linux Utilities
```bash
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git nginx curl
```

### Step 2: Clone Repository
```bash
git clone https://github.com/LetscodeJosh/PIMS-Territory-Reconfig-Portal.git ~/pims-portal
cd ~/pims-portal
```

### Step 3: Create Python Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure systemd 24/7 Background Service
Create the service configuration file:
```bash
sudo bash -c "cat << 'EOF' > /etc/systemd/system/pims-portal.service
[Unit]
Description=PIMS Territory Reconfiguration Portal (Pure GCP Bare-Metal Streamlit Service)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/pims-portal
ExecStart=$HOME/pims-portal/venv/bin/streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
Restart=always
RestartSec=5s

Environment=PYTHONUNBUFFERED=1
Environment=LC_ALL=C.UTF-8
Environment=LANG=C.UTF-8

NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$HOME/pims-portal

LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF"
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pims-portal.service
sudo systemctl start pims-portal.service
```

### Step 5: Configure Nginx Reverse Proxy
Copy the pre-tuned configuration to Nginx:
```bash
sudo cp ~/pims-portal/deploy/gcp/nginx-pims.conf /etc/nginx/sites-available/pims-portal
sudo ln -sf /etc/nginx/sites-available/pims-portal /etc/nginx/sites-enabled/pims-portal
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### Step 6: Verify Deployment
Open your browser and navigate to:
```
http://<YOUR_GCP_VM_EXTERNAL_IP>
```

---

## 🔧 Day-to-Day Operations & Service Management

| Operation | Command |
|---|---|
| **Check service health** | `sudo systemctl status pims-portal` |
| **View live logs** | `sudo journalctl -u pims-portal -f` |
| **Restart portal** | `sudo systemctl restart pims-portal` |
| **Stop portal** | `sudo systemctl stop pims-portal` |
| **Restart Nginx** | `sudo systemctl restart nginx` |
| **Check Nginx syntax** | `sudo nginx -t` |

---

## 🔄 Updating to Latest App Releases

When new bug fixes or features are pushed to GitHub, update your live VM in 5 seconds via PuTTY:

```bash
cd ~/pims-portal
bash deploy/gcp/update.sh
```

Or manually:
```bash
cd ~/pims-portal
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart pims-portal
```

---

## 🔒 Optional: Add Custom Domain & Free SSL (HTTPS)

If you assign a custom domain name (e.g. `territory.yourcompany.com`) pointing to your GCP VM's External IP address:

Run the 1-click Let's Encrypt SSL setup script:
```bash
cd ~/pims-portal
bash deploy/gcp/setup_ssl.sh territory.yourcompany.com
```

This will automatically:
1. Install Certbot.
2. Update Nginx configuration for your domain.
3. Obtain a free trusted SSL/TLS certificate from Let's Encrypt.
4. Enforce automatic HTTP $\rightarrow$ HTTPS redirection.
5. Configure automatic 90-day renewal.

---

## 🩺 Troubleshooting Guide

### 1. Browser shows "Cannot connect" or timeout
* Verify GCP VPC firewall rules: In GCP Console $\rightarrow$ **VPC network** $\rightarrow$ **Firewall**, make sure rule `default-allow-http` (port 80) is applied to your VM target.
* Check if Nginx is running: `sudo systemctl status nginx`.

### 2. Streamlit displays "Connecting..." or WebSocket error
* Verify Nginx reverse proxy configuration: `cat /etc/nginx/sites-enabled/pims-portal`.
* Ensure WebSocket upgrade headers (`Upgrade $http_upgrade`, `Connection $connection_upgrade`) are active.
* Test internal Streamlit health: `curl http://127.0.0.1:8501/_stcore/health` (should return `ok`).

### 3. ERPNext login fails or network timeout
* Test connectivity from the VM to ERPNext:
  ```bash
  curl -I https://dev.pmii-marketing.com
  ```
* If using an internal or custom ERPNext endpoint, configure `~/pims-portal/.env`:
  ```bash
  cp .env.example .env
  nano .env
  # Set ERPNEXT_URL=https://your-live-domain.com
  sudo systemctl restart pims-portal
  ```

