# Google Cloud Platform (GCP) Deployment Guide
## PIMS Territory Reconfiguration Web Portal

This repository is fully configured and ready for production deployment to **Google Cloud Platform (GCP)**.

The recommended deployment target is **Google Cloud Run**, a serverless container platform that automatically scales from zero, includes free SSL certificates, provides a public HTTPS endpoint, and integrates with custom domains.

---

### 🌟 Recommended Architecture: Google Cloud Run

* **Runtime**: Containerized Python 3.11 (`Dockerfile`)
* **Port**: Automatically injected by Cloud Run (`$PORT`, defaults to `8080`)
* **Health Check**: Internal Streamlit health probe at `/_stcore/health`
* **Scaling**: `0` (scales down to $0 cost when idle) to `10+` instances on peak demand
* **Region**: `asia-southeast1` (Singapore) — lowest latency for users in the Philippines

---

## 🚀 Option 1: 1-Click Deployment via Google Cloud Console (Zero CLI Required)

This is the fastest and easiest method directly from your web browser:

1. **Log in to Google Cloud Console**:
   * Navigate to [https://console.cloud.google.com/run](https://console.cloud.google.com/run).
   * Select or create your GCP project.

2. **Create a Cloud Run Service**:
   * Click **`+ CREATE SERVICE`**.
   * Under **Deployment platform**, choose:
     `Continuously deploy from a repository (source repository)`
   * Click **`SET UP WITH CLOUD BUILD`**.

3. **Connect Your GitHub Repository**:
   * Repository Provider: **GitHub**.
   * Select Repository: `LetscodeJosh/PIMS-Territory-Reconfig-Portal`.
   * Branch: `^main$`.
   * Build Type: Select **`Dockerfile`**.
   * Source location: `/Dockerfile` (root directory).
   * Click **Save**.

4. **Configure Service Settings**:
   * **Service name**: `pims-territory-portal` (or your chosen name).
   * **Region**: Select `asia-southeast1 (Singapore)`.
   * **Authentication**: Check **`Allow unauthenticated invocations`** (allows users to access the web portal via HTTPS).
   * **Container, Networking, Security**:
     * **Container port**: `8080`.
     * **Memory**: `1 GiB` (or `2 GiB` for large masterlists).
     * **CPU**: `1`.
     * **Execution environment**: Default (Second generation).
     * **Min instances**: `0` (or `1` to eliminate cold starts).
     * **Max instances**: `10`.

5. **Set Environment Variables (Optional)**:
   * Under **Variables & Secrets** $\rightarrow$ **Add Variable**:
     * `ERPNEXT_URL`: `https://staging.pmii-marketing.com` (or your live ERPNext URL).
     * `STREAMLIT_SERVER_HEADLESS`: `true`.

6. **Deploy**:
   * Click **`CREATE`**.
   * Cloud Build will automatically build the Docker image and deploy it.
   * Within 2 minutes, you will receive a secure public URL:
     `https://pims-territory-portal-xxxx-as.a.run.app`

---

## ⚡ Option 2: Deploy via Google Cloud Shell (In-Browser CLI)

If you prefer using the command line without installing anything on your PC:

1. Open the [Google Cloud Console](https://console.cloud.google.com) and click the **Cloud Shell** icon (`>_`) in the top-right toolbar.
2. Clone the repository into Cloud Shell:
   ```bash
   git clone https://github.com/LetscodeJosh/PIMS-Territory-Reconfig-Portal.git
   cd PIMS-Territory-Reconfig-Portal
   ```
3. Run the 1-line Cloud Run deploy command:
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
4. When prompted:
   * Confirm source upload: press `Y`.
   * Cloud Build will package and deploy the container automatically.
   * The live service URL will be printed on completion.

---

## 🔄 Option 3: Automated CI/CD with Google Cloud Build (`cloudbuild.yaml`)

This repository includes a pre-configured `cloudbuild.yaml` file:

1. To trigger manual build and deployment via Cloud Build:
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```
2. To set up automatic deployment on every `git push`:
   * Go to **Cloud Build** $\rightarrow$ **Triggers** in the GCP Console.
   * Click **Create Trigger**.
   * Connect repository `LetscodeJosh/PIMS-Territory-Reconfig-Portal`.
   * Event: **Push to a branch** (`^main$`).
   * Configuration: **Cloud Build configuration file (yaml or json)** $\rightarrow$ Location: `cloudbuild.yaml`.
   * Click **Create**. Every commit pushed to `main` will automatically build and deploy to Cloud Run!

---

## 🍃 Option 4: Deploying to Google App Engine (`app.yaml`)

If your enterprise uses Google App Engine instead of Cloud Run:

1. This repository includes a pre-configured `app.yaml`.
2. In Google Cloud Shell or with `gcloud` installed:
   ```bash
   gcloud app deploy app.yaml
   ```
3. View your deployed portal:
   ```bash
   gcloud app browse
   ```

---

## 🌐 Post-Deployment: Custom Domain & SSL Setup

To map your company domain (e.g., `territory.yourcompany.com`) to Cloud Run:

1. In GCP Console, navigate to **Cloud Run** $\rightarrow$ **Custom Domains** (or **Manage Custom Domains**).
2. Click **`ADD MAPPING`**.
3. Select your Cloud Run service (`pims-territory-portal`).
4. Enter your custom domain name (e.g. `territory.pmii-marketing.com`).
5. Google Cloud will provide DNS records (CNAME or A/AAAA).
6. Add these records in your DNS provider (Cloudflare, GoDaddy, Google Domains, etc.).
7. Google Cloud automatically provisions and renews a free **managed SSL/TLS certificate**!

---

## 🔒 Security & Environment Variables

| Variable | Description | Default Value | Recommended Production Value |
|---|---|---|---|
| `PORT` | Container listen port | `8080` | `8080` (Injected by Cloud Run) |
| `ERPNEXT_URL` | Target ERPNext server endpoint | `https://staging.pmii-marketing.com` | `https://staging.pmii-marketing.com` |
| `PIMS_SERVICE_USER` | Optional service account user | `""` | Set via Secret Manager if used |
| `PIMS_SERVICE_PASSWORD` | Optional service account password | `""` | Set via Secret Manager if used |
| `ERPNEXT_INSECURE_SSL` | Disable TLS certificate checks | `0` | Strictly `0` in production |

---

## 🩺 Health Check & Monitoring

* **Health Probe**: `GET /_stcore/health` returns `200 OK` when the service is healthy.
* **Logs**: View live logs in **Cloud Logging** (`console.cloud.google.com/logs`) by querying:
  ```
  resource.type="cloud_run_revision"
  resource.labels.service_name="pims-territory-portal"
  ```
* **Metrics**: Real-time traffic, latency, CPU utilization, and container memory are monitored automatically under the Cloud Run **Metrics** tab.
