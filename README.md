# PIMS Territory Reconfiguration Portal (v.0.1.1)

Welcome to the **PIMS Territory Reconfiguration Portal** repository. This enterprise web application allows Sales Force Effectiveness (SFE) Leads and District Managers to reconfigure territories, manage MedRep resignations, execute portfolio doctor handovers, and review institution proposals with 1:1 ERPNext masterlist synchronization.

See [`RELEASE_NOTES.md`](./RELEASE_NOTES.md) for the complete `v.0.1.1` release notes and active feature matrix.

---

## 🚀 Deployment Options

This repository supports two production deployment models:

### Option 1: Pure GCP Compute Engine (Bare-Metal Linux via PuTTY) — Recommended for Enterprise
Deploy directly onto a **Google Cloud Platform (GCP) Compute Engine VM** using standard Linux tools (`systemd`, `nginx`, `python3-venv`).
* **Zero Docker, Zero Container Extensions**.
* Runs 24/7 as an autonomous background service (`pims-portal.service`).
* Includes Nginx reverse proxy with WebSocket support and optional free Let's Encrypt SSL.
* 👉 **Follow the complete step-by-step runbook in [`GCP_DEPLOYMENT_GUIDE.md`](./GCP_DEPLOYMENT_GUIDE.md)**.

**Quick 1-Command Installation via PuTTY:**
```bash
git clone https://github.com/LetscodeJosh/PIMS-Territory-Reconfig-Portal.git ~/pims-portal
cd ~/pims-portal
bash deploy/gcp/install.sh
```

---

### Option 2: Streamlit Community Cloud (Zero Server Management)
Deploy in 3 minutes via Streamlit's hosted cloud service:
1. Fork or push this repository to GitHub.
2. Sign in to **[share.streamlit.io](https://share.streamlit.io/)**.
3. Select this repository (`main` branch) with main file path `app.py`.
4. Add secrets in Streamlit Cloud Settings $\rightarrow$ Secrets if connecting to a custom ERPNext endpoint:
   ```toml
   ERPNEXT_URL = "https://your-erpnext-domain.com"
   ```
5. Click **Deploy!**

---

## 📁 Repository Structure

```
PIMS-Territory-Reconfig-Portal/
├── app.py                                  # Streamlit enterprise runner & gateway connector
├── requirements.txt                        # Python dependencies (streamlit>=1.35.0)
├── territory_reconfiguration_portal.html   # Standalone web app (1:1 ERPNext Tree, CRUD, Login)
├── index.html                              # Web app alias for hosting platforms
├── secure_frappe_gateway.py                # Cyber-grade Frappe API proxy & anti-BOLA/IDOR sentinel
├── .env.example                            # Production environment template
├── GCP_DEPLOYMENT_GUIDE.md                 # Complete GCP bare-metal deployment runbook
├── RELEASE_NOTES.md                        # Formal release notes & UAT changelog
├── .streamlit/
│   └── config.toml                         # Port binding, theme & performance configuration
└── deploy/
    └── gcp/                                # Pure GCP bare-metal deployment suite
        ├── install.sh                      # Turnkey 1-command installer script
        ├── nginx-pims.conf                 # Hardened Nginx reverse proxy with WebSocket support
        ├── pims-portal.service             # Production systemd unit file (24/7 auto-restart)
        ├── update.sh                       # 1-command update script for future releases
        └── setup_ssl.sh                    # Free Let's Encrypt SSL certificate installer
```

---

## 🔒 Security & ERPNext Integration Standard

* **Zero Hardcoded Secrets**: All endpoints and service account credentials can be configured via environment variables (`.env`) or Streamlit secrets.
* **Masterlist Protection**: Permanent deletion is disabled in the web portal. Unused territories are safely archived to the Archive Vault.
* **Resilient Failover**: Cached structures and session recovery ensure the portal remains responsive during transient backend interruptions.
