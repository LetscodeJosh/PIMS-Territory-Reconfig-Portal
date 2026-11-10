# PIMS Territory Reconfiguration Portal (v.0.1.1) • Cloud Deployment Guide

See [`RELEASE_NOTES.md`](./RELEASE_NOTES.md) for the active `v.0.1.1` release notes, UAT fixes, and operational feature matrix.  
See [`GCP_DEPLOYMENT_GUIDE.md`](./GCP_DEPLOYMENT_GUIDE.md) for the complete, step-by-step **Google Cloud Platform (GCP)** deployment manual.

This repository is fully configured and containerized for deployment on:
1. **Google Cloud Platform (GCP)** — via **Google Cloud Run**, **Cloud Build**, or **Google App Engine** (Enterprise Containerized Standard).
2. **Streamlit Community Cloud** — 1-click free hosting.

---

## 📁 Repository Structure

```
├── Dockerfile                              # Production container for Google Cloud Run
├── .dockerignore                           # Build context exclusions
├── cloudbuild.yaml                         # Google Cloud Build CI/CD deployment pipeline
├── app.yaml                                # Google App Engine runtime configuration
├── app.py                                  # Streamlit cloud runner (full-screen responsive)
├── secure_frappe_gateway.py                # Server-side Frappe validation & session gateway
├── requirements.txt                        # Cloud container requirements
├── territory_reconfiguration_portal.html   # Complete interactive web app (1:1 ERPNext Tree, CRUD, Login)
├── index.html                              # High-speed static web asset
├── GCP_DEPLOYMENT_GUIDE.md                 # Detailed GCP Cloud Run & App Engine guide
├── RELEASE_NOTES.md                        # Active release notes & bug fix tracking
├── .streamlit/
│   └── config.toml                         # Enterprise theme & performance configuration
└── README.md                               # This deployment guide
```

---

## ☁️ Deploying to Google Cloud Platform (GCP)

### Method A: Google Cloud Run via Cloud Console (1-Click UI / Zero CLI)
1. Go to [console.cloud.google.com/run](https://console.cloud.google.com/run).
2. Click **Create Service** $\rightarrow$ **Continuously deploy from a repository**.
3. Connect your repository: `LetscodeJosh/PIMS-Territory-Reconfig-Portal` (`main` branch).
4. Select **Dockerfile** as the build type.
5. Select region `asia-southeast1 (Singapore)`.
6. Set port to `8080`, memory `1 GiB`, CPU `1`.
7. Select **Allow unauthenticated invocations** and click **Create**!

### Method B: Google Cloud Shell / `gcloud` CLI
Run directly in Google Cloud Shell:
```bash
gcloud run deploy pims-territory-portal \
  --source . \
  --region asia-southeast1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars ERPNEXT_URL=https://staging.pmii-marketing.com
```

### Method C: Automated CI/CD with Cloud Build
Trigger automated deployment on git push using `cloudbuild.yaml`:
```bash
gcloud builds submit --config cloudbuild.yaml
```

*For complete GCP custom domain mapping, SSL certificate setup, and cost optimization, refer to [`GCP_DEPLOYMENT_GUIDE.md`](./GCP_DEPLOYMENT_GUIDE.md).*

---

## 🚀 Deploying to Streamlit Community Cloud (Free)

1. Go to **[share.streamlit.io](https://share.streamlit.io/)**.
2. Click **Create app** $\rightarrow$ select `LetscodeJosh/PIMS-Territory-Reconfig-Portal` $\rightarrow$ branch `main` $\rightarrow$ file `app.py`.
3. In App Settings $\rightarrow$ **Secrets**, configure:
   ```toml
   ERPNEXT_URL = "https://staging.pmii-marketing.com"
   ```
4. Click **Deploy!**

---

## 📱 Cross-Device Installation (PWA)

Once deployed to GCP or Streamlit:
- **PC & Mac Desktop App**: Open in Chrome/Edge $\rightarrow$ click the **Install App** icon in the address bar.
- **iPhone / iPad**: Open in Safari $\rightarrow$ tap Share $\rightarrow$ **"Add to Home Screen"**.
- **Android**: Open in Chrome $\rightarrow$ tap `⋮` $\rightarrow$ **"Install app"** / **"Add to Home screen"**.
