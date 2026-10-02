# PIMS Territory Reconfiguration Portal • Streamlit Deployment

This folder contains the complete, deployment-ready files to host the **Territory Reconfiguration Web App** on **Streamlit Community Cloud (100% Free)**.

---

## 📁 Package Contents

```
Streamlit_Deployment/
├── app.py                                  # Streamlit cloud runner (full-screen responsive)
├── requirements.txt                        # Cloud container requirements (streamlit>=1.35.0)
├── territory_reconfiguration_portal.html   # Complete interactive web app (1:1 ERPNext Tree, CRUD, Login)
├── .streamlit/
│   └── config.toml                         # Enterprise theme & performance configuration
└── README.md                               # Deployment guide
```

---

## 🚀 How to Deploy to Streamlit Cloud in 3 Minutes (Free)

### Step 1: Create a GitHub Repository
1. Go to [github.com/new](https://github.com/new).
2. Name your repository (e.g. `pims-territory-portal`).
3. Set it to **Public** (required for free Streamlit Community Cloud hosting).
4. Upload all files from this folder (`app.py`, `requirements.txt`, `territory_reconfiguration_portal.html`, `.streamlit/config.toml`) into your new GitHub repository.

### Step 2: Sign In to Streamlit Community Cloud
1. Go to **[share.streamlit.io](https://share.streamlit.io/)**.
2. Click **"Continue with GitHub"** and authorize Streamlit.

### Step 3: Deploy Your App
1. Click the **"Create app"** button.
2. Select:
   - **Repository:** `your-username/pims-territory-portal`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** (Optional: customize your subdomain, e.g. `pims-territory.streamlit.app`)
3. Click **"Deploy!"**
4. Streamlit will build your app and give you a permanent live HTTPS link (e.g. `https://pims-territory.streamlit.app`).

---

## 📱 How Users Access & Install Across Devices

Once deployed, send the live link (`https://<your-app>.streamlit.app`) to your team:
- **PC & Mac Desktop App (1-Click PWA)**: Open in Chrome/Edge $\rightarrow$ click the **Install App** icon in the address bar to create a standalone Desktop icon.
- **iPhone / iPad App**: Open in Safari $\rightarrow$ tap Share $\rightarrow$ **"Add to Home Screen"**.
- **Android App**: Open in Chrome $\rightarrow$ tap `⋮` $\rightarrow$ **"Install app"** / **"Add to Home screen"**.
