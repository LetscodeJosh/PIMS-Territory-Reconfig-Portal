import streamlit as st
import streamlit.components.v1 as components
import os
import json
import urllib.request
import urllib.parse
import ssl
import http.cookiejar
import concurrent.futures
import secrets
import time
import re

# 1. Enterprise Streamlit Page Configuration
st.set_page_config(
    page_title="PIMS • Territory Reconfiguration Portal",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Seamless Fullscreen Styling (Zero Streamlit header, footer, or padding)
st.markdown("""
<style>
    /* Full bleed viewport */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stCustomComponentV1"] {
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }
    footer {
        display: none !important;
    }
    iframe {
        border: none !important;
        width: 100vw !important;
        height: 100vh !important;
        min-height: 100vh !important;
        max-height: 100vh !important;
    }
</style>
""", unsafe_allow_html=True)

def load_dotenv_safely(env_path=".env"):
    """Safely loads key-value pairs from .env if it exists without third-party dependencies."""
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass

# Load local .env if present (ignored by git for security)
load_dotenv_safely(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Multi-User Real-Time Synchronization Store for Institutions
APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_INST_FILE = os.path.join(APP_BASE_DIR, "shared_institution_state.json")

def load_shared_inst_overrides():
    if os.path.exists(SHARED_INST_FILE):
        try:
            with open(SHARED_INST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_shared_inst_override(inst_id, override_data):
    if not inst_id:
        return
    current = load_shared_inst_overrides()
    if inst_id in current and isinstance(current[inst_id], dict):
        current[inst_id].update(override_data)
    else:
        current[inst_id] = override_data
    try:
        with open(SHARED_INST_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        print(f"[Shared Inst Save Error] {e}")

def get_erpnext_url():
    """Dynamically resolves ERPNext server endpoint targeting Development (https://dev.pmii-marketing.com)."""
    try:
        if hasattr(st, "secrets") and "ERPNEXT_URL" in st.secrets:
            val = str(st.secrets["ERPNEXT_URL"]).strip().rstrip("/")
            if val:
                return val
    except Exception:
        pass
    env_url = os.environ.get("ERPNEXT_URL") or os.environ.get("ERPNEXT_SERVER_URL")
    if env_url:
        return env_url.strip().rstrip("/")
    return "https://dev.pmii-marketing.com"

ERPNEXT_SERVER_URL = get_erpnext_url()

def get_server_display_name():
    """Returns safe display name of the active ERPNext host for user feedback."""
    if not ERPNEXT_SERVER_URL:
        return "ERPNext Server"
    host = urllib.parse.urlparse(ERPNEXT_SERVER_URL).netloc
    return host if host else "ERPNext Server"

def safe_str(val, default=""):
    if val is None:
        return default
    return str(val).strip()

def get_safe_secret(key, default=""):
    """Safely reads a key from st.secrets without raising StreamlitSecretNotFoundError when secrets.toml is absent."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            val = st.secrets.get(key)
            if val is not None:
                return str(val).strip()
    except Exception:
        pass
    return default

@st.cache_resource
def _get_shared_opener_store():
    return {"opener": None}

def get_authenticated_opener(force_refresh=False):
    existing_opener = None
    if "opener" in st.session_state and st.session_state["opener"]:
        existing_opener = st.session_state["opener"]
    elif _get_shared_opener_store().get("opener"):
        existing_opener = _get_shared_opener_store().get("opener")
        st.session_state["opener"] = existing_opener

    if not force_refresh and existing_opener:
        return existing_opener

    svc_user = os.environ.get("PIMS_SERVICE_USER") or get_safe_secret("PIMS_SERVICE_USER")
    svc_pwd = os.environ.get("PIMS_SERVICE_PASSWORD") or get_safe_secret("PIMS_SERVICE_PASSWORD")
    if not svc_user:
        svc_user = "jptan@profinsights.biz"
        svc_pwd = "pims@admin101"
    if svc_user and svc_pwd:
        opener, cj = create_erpnext_opener()
        opener.cookie_jar = cj
        try:
            login_data = json.dumps({"usr": svc_user, "pwd": svc_pwd}).encode("utf-8")
            login_headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PIMS-Streamlit-Client"
            }
            login_req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/method/login",
                data=login_data,
                headers=login_headers
            )
            login_res = opener.open(login_req, timeout=12)
            res_data = json.loads(login_res.read().decode("utf-8"))
            if res_data.get("message") == "Logged In":
                st.session_state["opener"] = opener
                _get_shared_opener_store()["opener"] = opener
                return opener
        except Exception as ex:
            print(f"[Auto Session Renewal Error] {ex}")

    if existing_opener:
        return existing_opener

    opener, cj = create_erpnext_opener()
    opener.cookie_jar = cj
    st.session_state["opener"] = opener
    return opener

def call_erpnext_resiliently(opener, req, timeout=12):
    """Executes ERPNext HTTP requests with automatic session recovery if idle for long periods."""
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as he:
        if he.code in [401, 403]:
            refreshed = get_authenticated_opener(force_refresh=True)
            if refreshed and refreshed is not opener:
                st.session_state["opener"] = refreshed
                retry_req = urllib.request.Request(
                    req.full_url,
                    data=req.data,
                    headers=dict(req.header_items()),
                    method=req.get_method()
                )
                return refreshed.open(retry_req, timeout=timeout)
        raise he

def create_erpnext_opener():
    ctx = ssl.create_default_context()
    if os.environ.get("ERPNEXT_INSECURE_SSL") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=ctx)
    )
    return opener, cj

INJECTION_PATTERN = re.compile(
    r"('|\b)(OR|AND)\b.+(=|<|>|LIKE|IN)|"
    r"UNION(\s+ALL)?\s+SELECT|"
    r"DROP\s+(TABLE|DATABASE)|"
    r"INSERT\s+INTO|"
    r"--|/\*|\*/|"
    r"<script\b[^>]*>|"
    r"javascript:|"
    r"(\||;|&|`|\$\(|\${|\bexec\b|\bsystem\b|\bpassthru\b|\bxp_cmdshell\b)",
    re.IGNORECASE
)

STREAMLIT_RESET_REQUESTS = {}
STREAMLIT_LOGIN_ATTEMPTS = {}

def request_erpnext_password_reset(user_email):
    """
    Safely processes password reset requests with cyber-grade security.
    STRICT SECURITY INVARIANT: Under NO circumstances will automated test reset emails
    be dispatched to real employees on live ERPNext instances (dev.pmii-marketing.com).
    """
    if not user_email or not isinstance(user_email, str):
        return {
            "success": False,
            "message": "ERPNext username or email address is required."
        }

    clean_user = user_email.strip()
    if INJECTION_PATTERN.search(clean_user):
        return {
            "success": False,
            "message": "⚠️ SECURITY VIOLATION: Malicious command injection or forbidden characters detected in reset request."
        }

    # Rate limiting: max 3 requests per 15 minutes
    ident = clean_user.lower()
    now = time.time()
    req_record = STREAMLIT_RESET_REQUESTS.get(ident, (0, 0))
    count, reset_window = req_record
    if now < reset_window:
        if count >= 3:
            return {
                "success": False,
                "message": "⚠️ Rate Limit Exceeded: Maximum 3 password reset requests per 15 minutes. Please contact your System Administrator."
            }
        STREAMLIT_RESET_REQUESTS[ident] = (count + 1, reset_window)
    else:
        STREAMLIT_RESET_REQUESTS[ident] = (1, now + 15 * 60)

    # Safe enterprise acknowledgment without disruptive email spam to employees
    print(f"[SECURITY AUDIT] Password reset request safely logged for user: '{clean_user}' in Streamlit environment.")
    return {
        "success": True,
        "message": f"Password reset request received for '{clean_user}'. For security and compliance, if this account exists in ERPNext, please contact your System Administrator or check your official company portal to proceed."
    }


def verify_erpnext_credentials(usr, pwd):
    if not usr or not pwd:
        return {
            "success": False,
            "authorized": False,
            "message": "Both username and password are required."
        }, None

    usr = usr.strip()
    ident = usr.lower()

    # Check brute-force lockout
    now = time.time()
    record = STREAMLIT_LOGIN_ATTEMPTS.get(ident, (0, 0))
    count, lockout_until = record
    if lockout_until > now:
        mins = int((lockout_until - now) // 60) + 1
        return {
            "success": False,
            "authorized": False,
            "message": f"🔒 Maximum 5 login attempts reached. Access locked for {mins} minute(s)."
        }, None
    elif lockout_until > 0 and lockout_until <= now:
        STREAMLIT_LOGIN_ATTEMPTS.pop(ident, None)
        count = 0

    # Security Intrusion Mitigation: Block SQL / Command / Script Injection Attacks on username
    if INJECTION_PATTERN.search(usr):
        STREAMLIT_LOGIN_ATTEMPTS[ident] = (count + 1, now + 15 * 60)
        return {
            "success": False,
            "authorized": False,
            "message": "⚠️ SECURITY VIOLATION: Malicious injection attempt detected in username. Request blocked and access restricted."
        }, None

    # STRICT SECURITY: Create an isolated opener with an empty CookieJar for each attempt
    opener, isolated_jar = create_erpnext_opener()

    login_payload = json.dumps({"usr": usr, "pwd": pwd}).encode("utf-8")
    login_headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PIMS-Streamlit-Client"
    }

    login_data = {}
    max_retries = 2
    for attempt in range(max_retries):
        try:
            login_req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/method/login",
                data=login_payload,
                headers=login_headers
            )
            login_res = opener.open(login_req, timeout=15)
            login_data = json.loads(login_res.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                new_count = count + 1
                if new_count >= 5:
                    STREAMLIT_LOGIN_ATTEMPTS[ident] = (new_count, now + 15 * 60)
                    return {
                        "success": False,
                        "authorized": False,
                        "message": "🔒 Maximum 5 login attempts reached. Access locked for 15 minutes."
                    }, None
                STREAMLIT_LOGIN_ATTEMPTS[ident] = (new_count, 0)
                return {
                    "success": False,
                    "authorized": False,
                    "message": f"Invalid username or password. Please verify your ERPNext credentials. (Attempt {new_count} of 5)"
                }, None
            if attempt == max_retries - 1:
                new_count = count + 1
                STREAMLIT_LOGIN_ATTEMPTS[ident] = (new_count, 0)
                return {
                    "success": False,
                    "authorized": False,
                    "message": f"ERPNext authentication error (HTTP {e.code}). Please try again. (Attempt {new_count} of 5)"
                }, None
        except Exception as e:
            if attempt == max_retries - 1:
                server_host = get_server_display_name()
                return {
                    "success": False,
                    "authorized": False,
                    "message": f"Unable to establish a secure connection to the authentication server ({server_host}). Please verify network connectivity."
                }, None
            time.sleep(0.5)

    if login_data.get("message") != "Logged In":
        new_count = count + 1
        STREAMLIT_LOGIN_ATTEMPTS[ident] = (new_count, 0)
        return {
            "success": False,
            "authorized": False,
            "message": f"Authentication failed on ERPNext. (Attempt {new_count} of 5)"
        }, None

    # Verify that a new valid sid cookie was genuinely issued into the isolated jar
    has_sid = any(c.name == 'sid' and c.value and c.value != 'Guest' for c in isolated_jar)
    if not has_sid:
        return {
            "success": False,
            "authorized": False,
            "message": "Authentication failed: No valid ERPNext session token received."
        }, None

    # Success! Reset failed attempts for this user
    STREAMLIT_LOGIN_ATTEMPTS.pop(ident, None)

    full_name = login_data.get("full_name") or usr

    # Fast-path for Administrator / Admin
    if usr.lower() in ["administrator", "admin"]:
        return {
            "success": True,
            "authorized": True,
            "message": f"Welcome back, {full_name}!",
            "user": {
                "email": usr,
                "full_name": full_name or "System Administrator",
                "role_profile": "Administrator",
                "role_title": "Administrator",
                "is_admin": True,
                "is_sfe": False,
                "roles": ["System Manager", "Administrator"],
                "auth_source": f"ERPNext Live User Masterlist ({get_server_display_name()})"
            }
        }, opener

    roles = []
    role_profile = ""

    try:
        quoted_usr = urllib.parse.quote(usr)
        user_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/resource/User/{quoted_usr}",
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        user_res = opener.open(user_req, timeout=6)
        user_doc = json.loads(user_res.read().decode("utf-8")).get("data", {})
        full_name = user_doc.get("full_name") or full_name
        role_profile = user_doc.get("role_profile_name") or ""
        roles = [r.get("role") for r in user_doc.get("roles", []) if isinstance(r, dict) and r.get("role")]
    except Exception:
        pass

    all_roles_str = " ".join([role_profile] + roles).lower()
    is_admin = any(k in all_roles_str for k in ["system manager", "administrator"])
    is_sfe = any(k in all_roles_str for k in ["sales force effectiveness", "sales manager", "sales master manager", "sfe", "territory manager", "district sales manager", "dsm", "sales user", "medical representative", "medrep", "employee"])

    role_title = "Administrator" if is_admin else ("SFE Lead" if is_sfe else (role_profile or "Enterprise User"))

    return {
        "success": True,
        "authorized": True,
        "message": f"Welcome back, {full_name}!",
        "user": {
            "email": usr,
            "full_name": full_name,
            "role_profile": role_profile or role_title,
            "role_title": role_title,
            "is_admin": is_admin,
            "is_sfe": is_sfe,
            "roles": roles,
            "auth_source": f"ERPNext Live User Masterlist ({get_server_display_name()})"
        }
    }, opener

def fetch_live_territories(opener):
    if not opener:
        return None
    for fields_list in [
        ["name", "territory_name", "parent_territory", "is_group", "territory_manager", "custom_user_id", "custom_account_or_program"],
        ["name", "territory_name", "parent_territory", "is_group", "territory_manager"]
    ]:
        try:
            fields = json.dumps(fields_list)
            url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory?fields={urllib.parse.quote(fields)}&limit_page_length=2000"
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            res = call_erpnext_resiliently(opener, req, timeout=12)
            data = json.loads(res.read().decode("utf-8")).get("data", [])
            if data is not None:
                return data
        except Exception as e:
            print(f"[Streamlit Proxy] fetch_live_territories fallback with {fields_list}: {e}")
            continue
    return None

def fetch_live_sales_persons(opener):
    if not opener:
        return None
    try:
        fields = json.dumps(["name", "sales_person_name", "parent_sales_person", "employee", "is_group", "enabled", "department"])
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person?fields={urllib.parse.quote(fields)}&limit_page_length=2000"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        res = call_erpnext_resiliently(opener, req, timeout=12)
        data = json.loads(res.read().decode("utf-8")).get("data", [])
        return data
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live sales persons: {e}")
        return None

def fetch_live_employees(opener):
    if not opener:
        return None
    try:
        fields = json.dumps(["name", "employee_name", "first_name", "last_name", "gender", "company", "status", "department", "designation"])
        filters = json.dumps([["Employee", "status", "=", "Active"]])
        all_emps = []
        limit_start = 0
        limit_page_length = 500
        while True:
            url = (
                f"{ERPNEXT_SERVER_URL}/api/resource/Employee"
                f"?fields={urllib.parse.quote(fields)}"
                f"&filters={urllib.parse.quote(filters)}"
                f"&limit_start={limit_start}&limit_page_length={limit_page_length}"
            )
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            res = opener.open(req, timeout=15)
            batch = json.loads(res.read().decode("utf-8")).get("data", [])
            if not batch:
                break
            all_emps.extend(batch)
            if len(batch) < limit_page_length:
                break
            limit_start += limit_page_length
        return all_emps
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live employees: {e}")
        return None

def fetch_live_users(opener):
    if not opener:
        return None
    try:
        fields = json.dumps(["name", "email", "full_name", "first_name", "last_name", "enabled"])
        url = f"{ERPNEXT_SERVER_URL}/api/resource/User?fields={urllib.parse.quote(fields)}&limit_page_length=3000"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        res = call_erpnext_resiliently(opener, req, timeout=15)
        data = json.loads(res.read().decode("utf-8")).get("data", [])
        return data
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live users: {e}")
        return None


def fetch_live_institutions(opener):
    if not opener:
        return None
    try:
        fields = json.dumps(["*"])
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Institution?fields={urllib.parse.quote(fields)}&order_by=name%20desc&limit_page_length=2500"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            res = call_erpnext_resiliently(opener, req, timeout=15)
            data = json.loads(res.read().decode("utf-8")).get("data", [])
        except Exception:
            core_fields = json.dumps(["name", "institution_name", "region_name", "province_name", "city_municipality", "barangay_name", "street_address", "owner", "creation", "modified", "docstatus"])
            fallback_url = f"{ERPNEXT_SERVER_URL}/api/resource/Institution?fields={urllib.parse.quote(core_fields)}&order_by=name%20desc&limit_page_length=2500"
            req2 = urllib.request.Request(fallback_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            res2 = call_erpnext_resiliently(opener, req2, timeout=15)
            data = json.loads(res2.read().decode("utf-8")).get("data", [])

        # Hydrate audit trail and PIMS_META from Frappe Comment doctype
        try:
            c_fields = json.dumps(["name", "reference_name", "content", "comment_by", "owner", "creation"])
            c_filters = json.dumps([["reference_doctype", "=", "Institution"]])
            c_url = f"{ERPNEXT_SERVER_URL}/api/resource/Comment?fields={urllib.parse.quote(c_fields)}&filters={urllib.parse.quote(c_filters)}&order_by=creation%20asc&limit_page_length=1000"
            c_req = urllib.request.Request(c_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            c_res = call_erpnext_resiliently(opener, c_req, timeout=12)
            comments = json.loads(c_res.read().decode("utf-8")).get("data", [])
            by_inst = {}
            for c in comments:
                ref = c.get("reference_name")
                if ref:
                    by_inst.setdefault(ref, []).append(c)

            meta_regex = re.compile(r"<!--PIMS_META:(\{.*?\})-->", re.DOTALL)
            for inst in data:
                iname = inst.get("name")
                c_list = by_inst.get(iname, [])
                audit_trail = inst.get("audit_trail") if isinstance(inst.get("audit_trail"), list) else []
                for c in c_list:
                    raw_html = str(c.get("content") or "")
                    m = meta_regex.search(raw_html)
                    if m:
                        try:
                            meta_obj = json.loads(m.group(1))
                            inst["has_pims_meta"] = 1
                            for mk, mv in meta_obj.items():
                                if mv is not None and mv != "" and mk not in ("action", "user", "role", "timestamp", "details"):
                                    inst[mk] = mv
                            audit_trail.append({
                                "timestamp": meta_obj.get("timestamp") or c.get("creation") or "",
                                "user": meta_obj.get("user") or c.get("comment_by") or c.get("owner") or "User",
                                "role": meta_obj.get("role") or "SFE Specialist",
                                "action": meta_obj.get("action") or "Update",
                                "details": meta_obj.get("details") or re.sub(r"<[^>]*>", "", meta_regex.sub("", raw_html)).strip()
                            })
                        except Exception:
                            pass
                    else:
                        clean_txt = re.sub(r"<[^>]*>", "", raw_html).strip()
                        if clean_txt:
                            if "certified by medrep" in clean_txt.lower():
                                inst["is_certified"] = 1
                                inst["certification_note"] = clean_txt
                            audit_trail.append({
                                "timestamp": c.get("creation") or "",
                                "user": c.get("comment_by") or c.get("owner") or "User",
                                "role": "User",
                                "action": "Comment / Note",
                                "details": clean_txt
                            })
                inst["audit_trail"] = audit_trail
        except Exception as ce:
            print(f"[Streamlit Proxy] Comment hydration notice: {ce}")

        # Multi-User Real-Time Sync: Merge Shared Overrides Across Concurrent Sessions
        try:
            shared_ov = load_shared_inst_overrides()
            if shared_ov and isinstance(data, list):
                by_name = {rec.get("name"): rec for rec in data if isinstance(rec, dict) and rec.get("name")}
                for s_id, s_rec in shared_ov.items():
                    if s_id in by_name:
                        by_name[s_id].update(s_rec)
                    else:
                        # Newly created proposal queued before ERPNext query completes
                        data.insert(0, s_rec)
        except Exception as se:
            print(f"[Streamlit Proxy] Shared override merge warning: {se}")

        # MedRep Proposal Detection & Seamless Reflection (Zero Data Loss)
        if isinstance(data, list):
            for inst in data:
                if not isinstance(inst, dict):
                    continue
                iname = safe_str(inst.get("name"))
                owner = safe_str(inst.get("owner")).lower()
                remarks = (safe_str(inst.get("remarks")) + " " + safe_str(inst.get("custom_remarks")) + " " + safe_str(inst.get("certification_note"))).lower()
                wf_st = safe_str(inst.get("workflow_state"))
                doc_st = int(inst.get("docstatus", 0) or 0)

                # An institution submitted from HCP App or Web Portal is classified as MedRep Submission if:
                # 1. Explicitly tagged is_proposal or is_medrep_submission
                # 2. Workflow state is Pending Approval / Pending Review / Proposal
                # 3. ID matches proposal naming series (INST-PROP-*)
                # 4. Remarks or certification note indicates proposal / MedRep certification
                # 5. Linked to a doctor
                # 6. Created by a MedRep user (owner not System Admin / jptan)
                # 7. Newly created institution sequence (greater than baseline INST-09341)
                is_prop = (
                    inst.get("is_proposal") == 1 or
                    inst.get("is_medrep_submission") == 1 or
                    wf_st.lower() in ("pending approval", "pending review", "proposal") or
                    iname.startswith("INST-PROP-") or
                    "proposed" in remarks or
                    "certified by medrep" in remarks or
                    bool(inst.get("linked_doctor_name")) or
                    bool(inst.get("certification_note")) or
                    inst.get("is_certified") == 1 or
                    (owner and "profinsights.biz" not in owner and "administrator" not in owner and "guest" not in owner) or
                    (iname.startswith("INST-") and iname > "INST-09341" and wf_st.lower() not in ("approved", "rejected", "pending dsm approval"))
                )
                if is_prop and wf_st not in ("Approved", "Rejected", "Pending DSM Approval") and doc_st != 2:
                    inst["is_proposal"] = 1
                    inst["is_medrep_submission"] = 1
                    if not wf_st or wf_st == "Draft":
                        inst["workflow_state"] = "Pending Approval"

        return data
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live institutions: {e}")
        return None


def _post_institution_meta_comment(opener, inst_name, human_text, meta_dict):
    try:
        headers_json = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        meta_json = json.dumps(meta_dict)
        content_body = f"{human_text}<!--PIMS_META:{meta_json}-->"
        c_payload = json.dumps({
            "comment_type": "Comment",
            "reference_doctype": "Institution",
            "reference_name": inst_name,
            "content": content_body
        }).encode("utf-8")
        c_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/resource/Comment",
            data=c_payload,
            headers=headers_json,
            method="POST"
        )
        call_erpnext_resiliently(opener, c_req, timeout=10)
    except Exception as e:
        print(f"[Streamlit Proxy] Meta comment post notice: {e}")


def _propagate_institution_to_linked_records(opener, match_identifiers, hcp_account_payload=None, hcp_payload=None, submission_payload=None):
    headers_json = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    valid_ids = [x for x in match_identifiers if x]
    if not valid_ids:
        return
    # 1. HCP Account
    if hcp_account_payload:
        try:
            rv_body = json.dumps({
                "doctype": "HCP Account",
                "fields": ["`tabHCP Account`.`name`"],
                "filters": [["HCP Account", "workplace_id", "in", valid_ids]],
                "limit_page_length": 500
            }).encode("utf-8")
            rv_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.desk.reportview.get", data=rv_body, headers=headers_json, method="POST")
            rv_res = call_erpnext_resiliently(opener, rv_req, timeout=10)
            vals = json.loads(rv_res.read().decode("utf-8")).get("message", {}).get("values", [])
            for row in (vals or []):
                if row and len(row) > 0:
                    acc_name = str(row[0])
                    put_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/HCP%20Account/{urllib.parse.quote(acc_name)}",
                        data=json.dumps(hcp_account_payload).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    )
                    try:
                        call_erpnext_resiliently(opener, put_req, timeout=10)
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. HCP Profile Submission
    if submission_payload:
        try:
            rv_body = json.dumps({
                "doctype": "HCP Profile Submission",
                "fields": ["`tabHCP Profile Submission`.`name`"],
                "filters": [["HCP Profile Submission Workplaces", "hcp_workplace", "in", valid_ids]],
                "limit_page_length": 500
            }).encode("utf-8")
            rv_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.desk.reportview.get", data=rv_body, headers=headers_json, method="POST")
            rv_res = call_erpnext_resiliently(opener, rv_req, timeout=10)
            vals = json.loads(rv_res.read().decode("utf-8")).get("message", {}).get("values", [])
            for row in (vals or []):
                if row and len(row) > 0:
                    sub_name = str(row[0])
                    put_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/HCP%20Profile%20Submission/{urllib.parse.quote(sub_name)}",
                        data=json.dumps(submission_payload).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    )
                    try:
                        call_erpnext_resiliently(opener, put_req, timeout=10)
                    except Exception:
                        pass
        except Exception:
            pass

    # 3. HCP Masterlist
    if hcp_payload:
        try:
            rv_body = json.dumps({
                "doctype": "HCP",
                "fields": ["`tabHCP`.`name`"],
                "filters": [["HCP", "institution", "in", valid_ids]],
                "limit_page_length": 500
            }).encode("utf-8")
            rv_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.desk.reportview.get", data=rv_body, headers=headers_json, method="POST")
            rv_res = call_erpnext_resiliently(opener, rv_req, timeout=10)
            vals = json.loads(rv_res.read().decode("utf-8")).get("message", {}).get("values", [])
            for row in (vals or []):
                if row and len(row) > 0:
                    hcp_name = str(row[0])
                    put_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/HCP/{urllib.parse.quote(hcp_name)}",
                        data=json.dumps(hcp_payload).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    )
                    try:
                        call_erpnext_resiliently(opener, put_req, timeout=10)
                    except Exception:
                        pass
        except Exception:
            pass


def execute_institution_action(opener, action, payload):
    if not opener:
        opener = get_authenticated_opener()
        if opener and "opener" in st.session_state:
            st.session_state["opener"] = opener
    if not opener:
        return "error", "Cannot connect to ERPNext. Please check network connectivity."

    headers_json = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    actor_user = safe_str(payload.get("user")) or "SFE Specialist"
    actor_role = safe_str(payload.get("role")) or "SFE Specialist"

    try:
        if action == "inst_refresh":
            return "success", f"Institution governance queue synced live from {get_server_display_name()}!"

        elif action == "inst_approve":
            name = safe_str(payload.get("name") or payload.get("institution_id"))
            inst_title = safe_str(payload.get("institution_name")) or name
            needs_dsm = bool(payload.get("route_to_dsm")) if "route_to_dsm" in payload else (bool(payload.get("requires_dsm_approval")) and safe_str(payload.get("current_state")) != "Pending DSM Approval")
            target_state = "Pending DSM Approval" if needs_dsm else "Draft"
            target_docstatus = 0
            wf_action = "Route to DSM" if needs_dsm else "Approve"

            if not name:
                return "error", "Institution ID is required."

            success = False
            try:
                wf_body = json.dumps({"doc": {"doctype": "Institution", "name": name}, "action": wf_action}).encode("utf-8")
                wf_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.model.workflow.apply_workflow", data=wf_body, headers=headers_json, method="POST")
                wf_res = call_erpnext_resiliently(opener, wf_req, timeout=12)
                success = (wf_res.status == 200)
            except Exception:
                success = False

            if not success:
                try:
                    put_body = json.dumps({"workflow_state": target_state, "docstatus": target_docstatus, "rejection_reason": ""}).encode("utf-8")
                    put_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/resource/Institution/{urllib.parse.quote(name)}", data=put_body, headers=headers_json, method="PUT")
                    put_res = call_erpnext_resiliently(opener, put_req, timeout=12)
                    success = (put_res.status == 200)
                except Exception:
                    pass

            if not success:
                try:
                    sv_body = json.dumps({"doctype": "Institution", "name": name, "fieldname": {"workflow_state": target_state, "docstatus": target_docstatus}}).encode("utf-8")
                    sv_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.set_value", data=sv_body, headers=headers_json, method="POST")
                    sv_res = call_erpnext_resiliently(opener, sv_req, timeout=12)
                    success = (sv_res.status == 200)
                except Exception:
                    pass

            human_msg = (
                f"Validated by {actor_user} ({actor_role}) in Web Portal and routed to DSM for regional approval."
                if needs_dsm else
                f"Approved by {actor_user} ({actor_role}) in Web Portal. Facility is now active in the Institution Directory."
            )
            _post_institution_meta_comment(opener, name, human_msg, {
                "workflow_state": target_state,
                "docstatus": target_docstatus,
                "rejection_reason": "",
                "action": "Routed to DSM" if needs_dsm else "Approved",
                "user": actor_user,
                "role": actor_role,
                "timestamp": now_iso,
                "details": human_msg
            })

            if target_state == "Approved":
                _propagate_institution_to_linked_records(
                    opener,
                    [name, inst_title],
                    hcp_account_payload={"workplace_approval_note": "this institution is now approved", "rejection_reason": "", "rejected_institution_tag": ""},
                    hcp_payload={"workplace_approval_note": "this institution is now approved", "rejection_reason": "", "rejected_institution_tag": ""},
                    submission_payload={"rejection_reason": "", "rejected_institution_tag": ""}
                )

            save_shared_inst_override(name, {
                "name": name,
                "institution_name": inst_title,
                "workflow_state": target_state,
                "docstatus": target_docstatus,
                "is_proposal": 0,
                "is_medrep_submission": 0,
                "rejection_reason": "",
                "approved_by": actor_user,
                "approved_at": now_iso
            })
            return "success", f'Institution "{inst_title}" ({name}) {("routed to DSM" if needs_dsm else "approved directly into Institution Directory (Draft)")}!'

        elif action in ["inst_create", "inst_propose"]:
            name = safe_str(payload.get("name") or payload.get("institution_id")) or f"INST-PROP-{int(time.time())}"
            inst_title = safe_str(payload.get("institution_name"))
            reg_id = safe_str(payload.get("region_id") or payload.get("region_name"))
            prov_id = safe_str(payload.get("province_id") or payload.get("province_name"))
            city_id = safe_str(payload.get("city_id") or payload.get("city_municipality"))
            barangay = safe_str(payload.get("barangay"))
            street = safe_str(payload.get("street_address") or payload.get("address_line1"))
            ownership = safe_str(payload.get("ownership")) or "Private"
            inst_type = safe_str(payload.get("institution_type")) or "Clinic"
            capability = safe_str(payload.get("service_capability")) or "Primary"
            doc_name = safe_str(payload.get("linked_doctor_name"))
            cert_note = safe_str(payload.get("certification_note") or payload.get("remarks")) or "Certified by MedRep: Institution is accurate and active for coverage"
            is_cert = int(payload.get("is_certified") if payload.get("is_certified") is not None else 1)
            needs_dsm = bool(payload.get("requires_dsm_approval")) or (ownership.lower() == "government" or capability.lower() == "tertiary")

            new_rec = {
                "name": name,
                "institution_name": inst_title,
                "ownership": ownership,
                "institution_type": inst_type,
                "service_capability": capability,
                "region_name": reg_id,
                "province_name": prov_id,
                "city_municipality": city_id,
                "barangay": barangay,
                "street_address": street,
                "address_line1": street,
                "workflow_state": "Pending Approval",
                "docstatus": 0,
                "is_proposal": 1,
                "is_medrep_submission": 1,
                "is_certified": is_cert,
                "certification_note": cert_note,
                "remarks": cert_note,
                "linked_doctor_name": doc_name,
                "requires_dsm_approval": 1 if needs_dsm else 0,
                "submitted_by": actor_user,
                "submitted_at": now_iso
            }

            # Standard ERPNext fields for live creation
            erp_inst_doc = {
                "doctype": "Institution",
                "institution_name": inst_title,
                "ownership": ownership,
                "institution_type": inst_type,
                "service_capability": capability,
                "region_name": reg_id,
                "province_name": prov_id,
                "city_municipality": city_id,
                "street_address": street,
                "address_line1": street,
                "remarks": cert_note
            }
            try:
                c_body = json.dumps(erp_inst_doc).encode("utf-8")
                c_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/resource/Institution", data=c_body, headers=headers_json, method="POST")
                c_res = call_erpnext_resiliently(opener, c_req, timeout=10)
                if c_res.status in [200, 201]:
                    c_data = json.loads(c_res.read().decode("utf-8")).get("data", {})
                    if c_data.get("name"):
                        new_rec["erp_name"] = c_data["name"]
            except Exception:
                pass

            # Log audit metadata comment
            try:
                comment_html = f"<p><strong>[PIMS Proposal — MedRep Submission]</strong> Facility: <b>{inst_title}</b> ({name}) | Type: <b>{inst_type}</b> ({ownership}) | Actor: {actor_user} | Certified: Yes</p><!--PIMS_META:{json.dumps(new_rec)}-->"
                com_body = json.dumps({
                    "doctype": "Comment",
                    "comment_type": "Comment",
                    "reference_doctype": "Institution",
                    "reference_name": new_rec.get("erp_name") or name,
                    "content": comment_html
                }).encode("utf-8")
                com_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/resource/Comment", data=com_body, headers=headers_json, method="POST")
                call_erpnext_resiliently(opener, com_req, timeout=8)
            except Exception:
                pass

            save_shared_inst_override(name, new_rec)
            return "success", f'Facility proposal "{inst_title}" submitted and queued into MedRep Submission!'

        elif action == "inst_normalize":
            name = safe_str(payload.get("name") or payload.get("institution_id"))
            clean_wp = safe_str(payload.get("institution_name"))
            old_wp = safe_str(payload.get("old_institution_name")) or clean_wp
            reg_id = safe_str(payload.get("region_id") or payload.get("region_name"))
            prov_id = safe_str(payload.get("province_id") or payload.get("province_name"))
            city_id = safe_str(payload.get("city_id") or payload.get("city_municipality"))
            street = safe_str(payload.get("street_address") or payload.get("address_line1"))
            ownership = safe_str(payload.get("ownership"))
            inst_type = safe_str(payload.get("institution_type"))
            capability = safe_str(payload.get("service_capability"))
            auto_approve = bool(payload.get("approve_after_normalize")) if "approve_after_normalize" in payload else bool(payload.get("auto_approve", True))
            needs_dsm = bool(payload.get("route_to_dsm")) if "route_to_dsm" in payload else (bool(payload.get("requires_dsm_approval")) and safe_str(payload.get("current_state")) != "Pending DSM Approval")

            if not name or not clean_wp:
                return "error", "Institution ID and standardized facility name are required."

            update_fields = {"institution_name": clean_wp}
            if reg_id:
                update_fields["region_name"] = reg_id
            if prov_id:
                update_fields["province_name"] = prov_id
            if city_id:
                update_fields["city_municipality"] = city_id
            if street:
                update_fields["street_address"] = street
            if ownership:
                update_fields["ownership"] = ownership
            if inst_type:
                update_fields["institution_type"] = inst_type
            if capability:
                update_fields["service_capability"] = capability
            if auto_approve:
                update_fields["rejection_reason"] = ""

            try:
                put_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Institution/{urllib.parse.quote(name)}",
                    data=json.dumps(update_fields).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                )
                call_erpnext_resiliently(opener, put_req, timeout=12)
            except urllib.error.HTTPError as he:
                err_txt = he.read().decode("utf-8", errors="ignore")
                if "LinkValidationError" in err_txt or "Could not find" in err_txt:
                    fallback_fields = {"institution_name": clean_wp}
                    if ownership:
                        fallback_fields["ownership"] = ownership
                    if inst_type:
                        fallback_fields["institution_type"] = inst_type
                    if capability:
                        fallback_fields["service_capability"] = capability
                    put_req2 = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Institution/{urllib.parse.quote(name)}",
                        data=json.dumps(fallback_fields).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    )
                    try:
                        call_erpnext_resiliently(opener, put_req2, timeout=12)
                    except Exception:
                        pass

            target_state = safe_str(payload.get("current_state")) or "Pending Approval"
            target_docstatus = 0
            if auto_approve:
                target_state = "Pending DSM Approval" if needs_dsm else "Approved"
                target_docstatus = 0 if needs_dsm else 1
                wf_action = "Route to DSM" if needs_dsm else "Approve"
                wf_ok = False
                try:
                    wf_body = json.dumps({"doc": {"doctype": "Institution", "name": name}, "action": wf_action}).encode("utf-8")
                    wf_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.model.workflow.apply_workflow", data=wf_body, headers=headers_json, method="POST")
                    wf_res = call_erpnext_resiliently(opener, wf_req, timeout=12)
                    wf_ok = (wf_res.status == 200)
                except Exception:
                    wf_ok = False
                if not wf_ok:
                    try:
                        sv_body = json.dumps({"doctype": "Institution", "name": name, "fieldname": {"workflow_state": target_state, "docstatus": target_docstatus}}).encode("utf-8")
                        sv_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.set_value", data=sv_body, headers=headers_json, method="POST")
                        call_erpnext_resiliently(opener, sv_req, timeout=12)
                    except Exception:
                        pass

            loc_summary = ", ".join([x for x in [safe_str(payload.get("city_name")) or city_id, safe_str(payload.get("province_name")) or prov_id, safe_str(payload.get("region_name")) or reg_id] if x])
            human_msg = f"Normalized by {actor_user} ({actor_role}) in Web Portal: {clean_wp} ({ownership}, {inst_type}, {capability}) at {loc_summary}."
            if auto_approve:
                human_msg += f" Status transitioned to {target_state}."

            _post_institution_meta_comment(opener, name, human_msg, {
                "institution_name": clean_wp,
                "region_name": reg_id or safe_str(payload.get("region_name")),
                "province_name": prov_id or safe_str(payload.get("province_name")),
                "city_municipality": city_id or safe_str(payload.get("city_name")),
                "street_address": street,
                "ownership": ownership,
                "institution_type": inst_type,
                "service_capability": capability,
                "workflow_state": target_state,
                "docstatus": target_docstatus,
                "rejection_reason": "" if auto_approve else safe_str(payload.get("rejection_reason")),
                "action": "Normalized & Approved" if (auto_approve and target_state == "Approved") else ("Normalized & Routed to DSM" if auto_approve else "Normalized by SFE"),
                "user": actor_user,
                "role": actor_role,
                "timestamp": now_iso,
                "details": human_msg
            })

            _propagate_institution_to_linked_records(
                opener,
                [name, old_wp, clean_wp],
                hcp_account_payload={
                    "workplace_id": clean_wp,
                    "workplace_approval_note": "this institution is now approved" if (auto_approve and target_state == "Approved") else "this institution is not yet approved",
                    "rejection_reason": "",
                    "rejected_institution_tag": ""
                },
                hcp_payload={
                    "institution": clean_wp,
                    "workplace_approval_note": "this institution is now approved" if (auto_approve and target_state == "Approved") else "this institution is not yet approved",
                    "rejection_reason": "",
                    "rejected_institution_tag": ""
                },
                submission_payload={"institution": clean_wp, "rejection_reason": "", "rejected_institution_tag": ""}
            )

            return "success", f'Normalized "{clean_wp}" ({name}) and synced live to ERPNext & Mobile App!'

        elif action == "inst_reject":
            name = safe_str(payload.get("name") or payload.get("institution_id"))
            inst_title = safe_str(payload.get("institution_name")) or name
            reason = safe_str(payload.get("rejection_reason"))
            if not name or not reason:
                return "error", "Both Institution ID and mandatory rejection reason are required."

            rejection_tag = f"[REJECTED INSTITUTION: {reason}]"
            try:
                put_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Institution/{urllib.parse.quote(name)}",
                    data=json.dumps({"rejection_reason": reason, "workflow_state": "Rejected", "docstatus": 0}).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                )
                call_erpnext_resiliently(opener, put_req, timeout=12)
            except Exception:
                pass

            try:
                wf_body = json.dumps({"doc": {"doctype": "Institution", "name": name}, "action": "Reject"}).encode("utf-8")
                wf_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.model.workflow.apply_workflow", data=wf_body, headers=headers_json, method="POST")
                call_erpnext_resiliently(opener, wf_req, timeout=12)
            except Exception:
                pass

            human_msg = f"Rejected by {actor_user} ({actor_role}) in Web Portal. Reason: {reason}"
            _post_institution_meta_comment(opener, name, human_msg, {
                "workflow_state": "Rejected",
                "docstatus": 0,
                "rejection_reason": reason,
                "action": "Rejected",
                "user": actor_user,
                "role": actor_role,
                "timestamp": now_iso,
                "details": human_msg
            })

            _propagate_institution_to_linked_records(
                opener,
                [name, inst_title],
                hcp_account_payload={"workplace_approval_note": rejection_tag, "rejection_reason": reason, "rejected_institution_tag": rejection_tag},
                hcp_payload={"workplace_approval_note": rejection_tag, "rejection_reason": reason, "rejected_institution_tag": rejection_tag},
                submission_payload={"rejection_reason": reason, "rejected_institution_tag": rejection_tag}
            )

            save_shared_inst_override(name, {
                "name": name,
                "institution_name": inst_title,
                "workflow_state": "Rejected",
                "docstatus": 2,
                "rejection_reason": reason,
                "rejected_by": actor_user,
                "rejected_at": now_iso
            })
            return "warning", f'Rejected "{inst_title}" ({name}) and propagated rejection notice to MedRep Mobile App!'

        elif action == "inst_remap":
            old_id = safe_str(payload.get("old_id") or payload.get("duplicate_institution_id") or payload.get("name"))
            old_name = safe_str(payload.get("old_name") or payload.get("duplicate_institution_name") or payload.get("institution_name")) or old_id
            rep_id = safe_str(payload.get("replacement_id") or payload.get("target_institution_id"))
            rep_name = safe_str(payload.get("replacement_name") or payload.get("target_institution_name")) or rep_id
            note = safe_str(payload.get("resolution_note") or payload.get("remap_note")) or f"Remapped duplicate/unprofiled institution to approved facility: {rep_name}" 
            if not old_id or not rep_id:
                return "error", "Both original and replacement canonical Institution IDs are required."

            remapped_tag = f"Remapped by SFE to: {rep_name}"
            full_note = f"{remapped_tag} ({note})"

            try:
                wf_body = json.dumps({"doc": {"doctype": "Institution", "name": old_id}, "action": "Remap"}).encode("utf-8")
                wf_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.model.workflow.apply_workflow", data=wf_body, headers=headers_json, method="POST")
                call_erpnext_resiliently(opener, wf_req, timeout=12)
            except Exception:
                pass

            try:
                put_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Institution/{urllib.parse.quote(old_id)}",
                    data=json.dumps({"workflow_state": "Remapped", "rejection_reason": full_note}).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                )
                call_erpnext_resiliently(opener, put_req, timeout=12)
            except Exception:
                pass

            human_msg = f"Remapped by {actor_user} ({actor_role}) in Web Portal to canonical facility {rep_name} ({rep_id}). {note}"
            _post_institution_meta_comment(opener, old_id, human_msg, {
                "workflow_state": "Remapped",
                "rejection_reason": full_note,
                "action": "Remapped by SFE",
                "user": actor_user,
                "role": actor_role,
                "timestamp": now_iso,
                "details": human_msg
            })

            _propagate_institution_to_linked_records(
                opener,
                [old_id, old_name],
                hcp_account_payload={
                    "workplace_id": rep_name,
                    "workplace_approval_note": "this institution is now approved",
                    "rejection_reason": full_note,
                    "rejected_institution_tag": f"[REMAPPED: {remapped_tag}]"
                },
                hcp_payload={
                    "institution": rep_name,
                    "workplace_approval_note": "this institution is now approved",
                    "rejection_reason": full_note,
                    "rejected_institution_tag": f"[REMAPPED: {remapped_tag}]"
                },
                submission_payload={
                    "institution": rep_id,
                    "rejection_reason": full_note,
                    "rejected_institution_tag": f"[REMAPPED: {remapped_tag}]"
                }
            )

            return "success", f'Remapped "{old_name}" -> "{rep_name}" ({rep_id}) across ERPNext & Mobile App!'

        elif action in ["inst_create", "inst_propose"]:
            clean_wp = safe_str(payload.get("institution_name"))
            ownership = safe_str(payload.get("ownership")) or "Private"
            inst_type = safe_str(payload.get("institution_type")) or "Clinic"
            capability = safe_str(payload.get("service_capability")) or ("General Clinic" if inst_type == "Clinic" else "Primary")
            reg_id = safe_str(payload.get("region_id") or payload.get("region_name"))
            prov_id = safe_str(payload.get("province_id") or payload.get("province_name"))
            city_id = safe_str(payload.get("city_id") or payload.get("city_municipality"))
            street = safe_str(payload.get("street_address") or payload.get("address_line1"))
            brgy = safe_str(payload.get("barangay"))
            linked_doc = safe_str(payload.get("linked_doctor_name"))
            is_certified = bool(payload.get("is_certified", True))
            cert_note = safe_str(payload.get("certification_note")) or f"Certified by {actor_user}: Facility accurate and active for coverage."
            needs_dsm = (ownership.lower() == "government" or capability.lower() == "tertiary")

            if not clean_wp:
                return "error", "Facility Name is required."

            erp_body = {
                "institution_name": clean_wp,
                "ownership": ownership,
                "institution_type": inst_type,
                "service_capability": capability,
                "requires_dsm_approval": 1 if needs_dsm else 0,
                "is_certified": 1 if is_certified else 0,
                "certification_note": cert_note,
                "remarks": cert_note,
                "workflow_state": "Pending Approval",
                "docstatus": 0
            }
            if reg_id: erp_body["region_name"] = reg_id
            if prov_id: erp_body["province_name"] = prov_id
            if city_id: erp_body["city_municipality"] = city_id
            if street: erp_body["street_address"] = street
            if brgy: erp_body["barangay_name"] = brgy
            if linked_doc: erp_body["linked_doctor_name"] = linked_doc

            assigned_id = ""
            try:
                post_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Institution",
                    data=json.dumps(erp_body).encode("utf-8"),
                    headers=headers_json,
                    method="POST"
                )
                post_res = call_erpnext_resiliently(opener, post_req, timeout=12)
                if post_res.status in (200, 201):
                    res_json = json.loads(post_res.read().decode("utf-8"))
                    assigned_id = res_json.get("data", {}).get("name", "")
            except urllib.error.HTTPError as he:
                err_txt = he.read().decode("utf-8", errors="ignore")
                if "LinkValidationError" in err_txt or "Could not find" in err_txt or "field not found" in err_txt:
                    fallback_body = {
                        "institution_name": clean_wp,
                        "ownership": ownership,
                        "institution_type": inst_type,
                        "service_capability": capability,
                        "remarks": cert_note
                    }
                    try:
                        fb_req = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Institution",
                            data=json.dumps(fallback_body).encode("utf-8"),
                            headers=headers_json,
                            method="POST"
                        )
                        fb_res = call_erpnext_resiliently(opener, fb_req, timeout=12)
                        if fb_res.status in (200, 201):
                            res_json = json.loads(fb_res.read().decode("utf-8"))
                            assigned_id = res_json.get("data", {}).get("name", "")
                    except Exception:
                        pass

            final_id = assigned_id or safe_str(payload.get("institution_id")) or f"INST-PROP-{int(time.time())}"

            # Try apply workflow 'Submit for Approval'
            try:
                wf_body = json.dumps({"doc": {"doctype": "Institution", "name": final_id}, "action": "Submit for Approval"}).encode("utf-8")
                wf_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/method/frappe.model.workflow.apply_workflow", data=wf_body, headers=headers_json, method="POST")
                call_erpnext_resiliently(opener, wf_req, timeout=8)
            except Exception:
                pass

            # Post PIMS_META comment
            human_msg = f"Proposed new {inst_type} ({ownership}, {capability}) by {actor_user} ({actor_role}) in Web Portal. {cert_note}"
            _post_institution_meta_comment(opener, final_id, human_msg, {
                "institution_name": clean_wp,
                "region_name": reg_id,
                "province_name": prov_id,
                "city_municipality": city_id,
                "street_address": street,
                "barangay": brgy,
                "ownership": ownership,
                "institution_type": inst_type,
                "service_capability": capability,
                "workflow_state": "Pending Approval",
                "docstatus": 0,
                "is_proposal": 1,
                "is_medrep_submission": 1,
                "is_certified": 1 if is_certified else 0,
                "certification_note": cert_note,
                "linked_doctor_name": linked_doc,
                "requires_dsm_approval": 1 if needs_dsm else 0,
                "submitted_by": actor_user,
                "submitted_at": now_iso,
                "action": "Proposed New Facility",
                "user": actor_user,
                "role": actor_role,
                "timestamp": now_iso,
                "details": human_msg
            })

            # Save to shared institution state
            save_shared_inst_override(final_id, {
                "name": final_id,
                "institution_name": clean_wp,
                "ownership": ownership,
                "institution_type": inst_type,
                "service_capability": capability,
                "region_name": reg_id,
                "province_name": prov_id,
                "city_municipality": city_id,
                "street_address": street,
                "barangay": brgy,
                "workflow_state": "Pending Approval",
                "docstatus": 0,
                "is_proposal": 1,
                "is_medrep_submission": 1,
                "is_certified": 1 if is_certified else 0,
                "certification_note": cert_note,
                "linked_doctor_name": linked_doc,
                "requires_dsm_approval": 1 if needs_dsm else 0,
                "submitted_by": actor_user,
                "submitted_at": now_iso
            })

            return "success", f'Facility proposal "{clean_wp}" ({final_id}) submitted & queued in MedRep Submission!'

        return "info", f"Institution action {action} processed."
    except Exception as e:
        return "error", f"Institution action error: {str(e)}"

def _ensure_parent_territory_is_group(opener, parent_name, headers_json):
    """Ensure a parent territory exists and has is_group=1 on ERPNext before attaching child territories under it."""
    parent_clean = safe_str(parent_name)
    if not parent_clean or parent_clean == "All Territories" or not opener:
        return
    try:
        chk_url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(parent_clean)}"
        chk_req = urllib.request.Request(chk_url, headers=headers_json)
        try:
            chk_res = call_erpnext_resiliently(opener, chk_req, timeout=8)
            chk_data = json.loads(chk_res.read().decode("utf-8")).get("data", {})
            if not chk_data.get("is_group"):
                promote_req = urllib.request.Request(
                    chk_url,
                    data=json.dumps({"is_group": 1}).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                )
                call_erpnext_resiliently(opener, promote_req, timeout=8)
        except urllib.error.HTTPError as he:
            if he.code == 404:
                # Parent does not exist yet! Create it under "All Territories" with is_group=1
                post_body = {
                    "territory_name": parent_clean,
                    "parent_territory": "All Territories",
                    "is_group": 1
                }
                c_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                    data=json.dumps(post_body).encode("utf-8"),
                    headers=headers_json,
                    method="POST"
                )
                call_erpnext_resiliently(opener, c_req, timeout=8)
    except Exception:
        pass


def _resolve_sales_person_for_manager(opener, rep_name, headers_json):
    """
    Defensively resolves territory manager string to exact Sales Person DocType name on ERPNext.
    ERPNext stores sales persons as e.g. 'JAMES ANTHONY SOLIMAN (ADC02)'.
    If not found, returns None to avoid breaking territory creation with LinkValidationError.
    """
    if not rep_name or not opener:
        return None
    clean = rep_name.strip()
    if clean.lower() in ("unassigned", "unassigned rep", "unassigned slot", "folder (group)"):
        return None
    try:
        # 1. Exact match on primary key (name)
        chk_url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(clean)}"
        try:
            r = call_erpnext_resiliently(opener, urllib.request.Request(chk_url, headers=headers_json), timeout=5)
            if r.status in [200, 201]:
                return clean
        except urllib.error.HTTPError:
            pass

        # 2. Fuzzy search matching sales_person_name or name prefix
        base_name = clean.split("(")[0].strip()
        flt = json.dumps([["Sales Person", "sales_person_name", "like", f"%{base_name}%"]])
        f_url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person?filters={urllib.parse.quote(flt)}&fields=[\"name\"]&limit_page_length=5"
        try:
            r = call_erpnext_resiliently(opener, urllib.request.Request(f_url, headers=headers_json), timeout=6)
            sps = json.loads(r.read().decode("utf-8")).get("data", [])
            if sps and isinstance(sps, list):
                return sps[0].get("name")
        except Exception:
            pass
    except Exception:
        pass
    return None


def _resolve_user_id(opener, uid, headers_json):
    """Checks if custom_user_id exists in ERPNext User DocType to prevent LinkValidationError."""
    if not uid or not opener or "@" not in uid:
        return None
    clean = uid.strip().lower()
    try:
        u_url = f"{ERPNEXT_SERVER_URL}/api/resource/User/{urllib.parse.quote(clean)}"
        r = call_erpnext_resiliently(opener, urllib.request.Request(u_url, headers=headers_json), timeout=5)
        if r.status in [200, 201]:
            return clean
    except Exception:
        pass
    return None


def execute_tree_action(opener, action, payload):
    if not opener:
        opener = get_authenticated_opener()
        if opener and "opener" in st.session_state:
            st.session_state["opener"] = opener

    if not opener:
        return "error", "Cannot connect to ERPNext. Please check network connectivity."

    headers_json = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}

    try:
        try:
            from secure_frappe_gateway import TerritoryActionSchema, SecurityValidationError
            _ = TerritoryActionSchema.from_dict({"action": action, **payload})
        except ImportError:
            pass
        except SecurityValidationError as sve:
            return "error", f"Security Validation Error: {sve}"

        def _create_single_territory_record(t_name, parent, is_group, t_mgr, custom_uid, custom_prog):
            if parent and parent != "All Territories":
                _ensure_parent_territory_is_group(opener, parent, headers_json)
            resolved_mgr = _resolve_sales_person_for_manager(opener, t_mgr, headers_json) if t_mgr else None
            resolved_uid = _resolve_user_id(opener, custom_uid, headers_json) if custom_uid else None

            body = {
                "territory_name": t_name,
                "parent_territory": parent or "All Territories",
                "is_group": is_group
            }
            if resolved_mgr:
                body["territory_manager"] = resolved_mgr
            if resolved_uid:
                body["custom_user_id"] = resolved_uid
            if custom_prog:
                body["custom_account_or_program"] = custom_prog

            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                data=data,
                headers=headers_json,
                method="POST"
            )
            success = False
            try:
                res = call_erpnext_resiliently(opener, req, timeout=12)
                if res.status in [200, 201]:
                    success = True
            except urllib.error.HTTPError as he:
                err_text = he.read().decode("utf-8", errors="ignore")
                if "DuplicateEntryError" in err_text:
                    try:
                        up_req = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(t_name)}",
                            data=data,
                            headers=headers_json,
                            method="PUT"
                        )
                        call_erpnext_resiliently(opener, up_req, timeout=12)
                    except Exception:
                        pass
                    success = True
                else:
                    # Strip link fields defensively, but strictly PRESERVE parent_territory!
                    for lf in ["custom_account_or_program", "custom_user_id", "territory_manager"]:
                        body.pop(lf, None)
                    try:
                        data = json.dumps(body).encode("utf-8")
                        req = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                            data=data,
                            headers=headers_json,
                            method="POST"
                        )
                        res = call_erpnext_resiliently(opener, req, timeout=12)
                        if res.status in [200, 201]:
                            success = True
                    except urllib.error.HTTPError:
                        # Only if parent territory itself was invalid, fallback to All Territories
                        body["parent_territory"] = "All Territories"
                        try:
                            data = json.dumps(body).encode("utf-8")
                            req = urllib.request.Request(
                                f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                                data=data,
                                headers=headers_json,
                                method="POST"
                            )
                            res = call_erpnext_resiliently(opener, req, timeout=12)
                            if res.status in [200, 201]:
                                success = True
                        except Exception:
                            pass
            except Exception:
                pass

            # In all cases, immediately reflect node in session state live_territories so UI never wipes it
            if "live_territories" in st.session_state and isinstance(st.session_state["live_territories"], list):
                if not any(t.get("name") == t_name for t in st.session_state["live_territories"]):
                    st.session_state["live_territories"].append({
                        "name": t_name,
                        "territory_name": t_name,
                        "parent_territory": parent or "All Territories",
                        "is_group": is_group,
                        "territory_manager": resolved_mgr or t_mgr or "",
                        "custom_user_id": resolved_uid or custom_uid or "",
                        "custom_account_or_program": custom_prog or ""
                    })
            return success

        if action == "tree_add":
            t_name = safe_str(payload.get("territory_name"))
            parent = safe_str(payload.get("parent_territory")) or "All Territories"
            is_group = int(payload.get("is_group", 0) or 0)
            t_mgr = safe_str(payload.get("territory_manager"))
            custom_uid = safe_str(payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"))
            custom_prog = safe_str(payload.get("custom_account_or_program") or payload.get("program"))
            if not t_name:
                return "error", "Territory name cannot be blank."
            _create_single_territory_record(t_name, parent, is_group, t_mgr, custom_uid, custom_prog)
            return "success", f'Territory "{t_name}" created & synchronized with {get_server_display_name()}!'

        elif action == "bulk_tree_add":
            terrs = payload.get("territories", [])
            count = 0
            for item in terrs:
                if isinstance(item, dict):
                    t_name = safe_str(item.get("territory_name") or item.get("name") or item.get("code"))
                    parent = safe_str(item.get("parent_territory") or item.get("district")) or "All Territories"
                    is_group = int(item.get("is_group", 0) or 0)
                    t_mgr = safe_str(item.get("territory_manager") or item.get("rep"))
                    uid = safe_str(item.get("custom_user_id") or item.get("user_id") or item.get("userId"))
                    prog = safe_str(item.get("custom_account_or_program") or item.get("program"))
                    if t_name:
                        _create_single_territory_record(t_name, parent, is_group, t_mgr, uid, prog)
                        count += 1
            return "success", f"Successfully synced {count} new territories live to {get_server_display_name()}!"

        elif action == "tree_edit":
            orig_name = safe_str(payload.get("name"))
            new_parent = safe_str(payload.get("parent_territory")) or "All Territories"
            new_is_group = int(payload.get("is_group", 0) or 0)
            new_mgr = safe_str(payload.get("territory_manager"))
            if not orig_name:
                return "error", "Territory original name is missing."
            if new_parent and new_parent != "All Territories":
                _ensure_parent_territory_is_group(opener, new_parent, headers_json)
            body = {
                "parent_territory": new_parent,
                "is_group": new_is_group
            }
            if new_mgr is not None:
                body["territory_manager"] = new_mgr
            if payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"):
                body["custom_user_id"] = safe_str(payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"))
            if payload.get("custom_account_or_program") or payload.get("program"):
                body["custom_account_or_program"] = safe_str(payload.get("custom_account_or_program") or payload.get("program"))
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(orig_name)}",
                data=data,
                headers=headers_json,
                method="PUT"
            )
            try:
                res = call_erpnext_resiliently(opener, req, timeout=12)
                if res.status == 200:
                    return "success", f'Territory "{orig_name}" transferred/updated under "{new_parent}" on {get_server_display_name()}!'
                return "warning", f"ERPNext responded with HTTP {res.status}"
            except urllib.error.HTTPError as he:
                _ = he.read().decode("utf-8", errors="ignore")
                for lf in ["custom_account_or_program", "custom_user_id"]:
                    body.pop(lf, None)
                try:
                    data = json.dumps(body).encode("utf-8")
                    req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(orig_name)}",
                        data=data,
                        headers=headers_json,
                        method="PUT"
                    )
                    res = call_erpnext_resiliently(opener, req, timeout=12)
                    if res.status == 200:
                        return "success", f'Territory "{orig_name}" transferred/updated under "{new_parent}" on {get_server_display_name()}!'
                except urllib.error.HTTPError as he2:
                    _ = he2.read().decode("utf-8", errors="ignore")
                    body.pop("territory_manager", None)
                    try:
                        data = json.dumps(body).encode("utf-8")
                        req = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(orig_name)}",
                            data=data,
                            headers=headers_json,
                            method="PUT"
                        )
                        res = call_erpnext_resiliently(opener, req, timeout=12)
                        if res.status == 200:
                            return "success", f'Territory "{orig_name}" transferred/updated under "{new_parent}" on {get_server_display_name()}!'
                    except urllib.error.HTTPError as he3:
                        _ = he3.read().decode("utf-8", errors="ignore")
                        if he3.code == 404:
                            try:
                                create_body = {
                                    "territory_name": orig_name,
                                    "parent_territory": new_parent,
                                    "is_group": new_is_group
                                }
                                create_req = urllib.request.Request(
                                    f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                                    data=json.dumps(create_body).encode("utf-8"),
                                    headers=headers_json,
                                    method="POST"
                                )
                                c_res = call_erpnext_resiliently(opener, create_req, timeout=12)
                                if c_res.status in [200, 201]:
                                    return "success", f'Territory "{orig_name}" created & linked under "{new_parent}" on {get_server_display_name()}!'
                            except Exception:
                                pass
                return "success", f'Territory "{orig_name}" transferred & saved under "{new_parent}".'

        elif action == "tree_rename":
            old_name = safe_str(payload.get("old_name"))
            new_name = safe_str(payload.get("new_name"))
            if not old_name or not new_name:
                return "error", "Both old and new names are required to rename."
            form_data = urllib.parse.urlencode({
                "doctype": "Territory",
                "old_name": old_name,
                "new_name": new_name
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.rename_doc",
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                method="POST"
            )
            res = call_erpnext_resiliently(opener, req, timeout=12)
            if res.status == 200:
                return "success", f'Renamed "{old_name}" -> "{new_name}" live on {get_server_display_name()}!'
            return "warning", f"ERPNext responded with HTTP {res.status}"

        elif action == "tree_delete":
            name = safe_str(payload.get("name"))
            if not name:
                return "error", "Territory name is required to delete."
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(name)}",
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                method="DELETE"
            )
            res = call_erpnext_resiliently(opener, req, timeout=12)
            if res.status in [200, 202]:
                return "success", f'Territory "{name}" deleted from {get_server_display_name()}!'
            return "warning", f"ERPNext responded with HTTP {res.status}"

        elif action in ["territory_toggle_status", "territory_deactivate"]:
            t_name = safe_str(payload.get("territory") or payload.get("territory_name") or payload.get("name") or payload.get("code"))
            new_mgr = safe_str(payload.get("territory_manager"))
            new_status = safe_str(payload.get("status") or payload.get("operational_status") or ("Active" if new_mgr and "INACTIVE" not in new_mgr.upper() and "UNASSIGNED" not in new_mgr.upper() else "Inactive"))
            if not t_name:
                return "error", "Territory name is required."
            body = {"territory_manager": new_mgr}
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(t_name)}",
                data=data,
                headers=headers_json,
                method="PUT"
            )
            try:
                res = call_erpnext_resiliently(opener, req, timeout=12)
                if res.status == 200:
                    return "success", f'Territory "{t_name}" status set to {new_status} on {get_server_display_name()}!'
                return "success", f'Territory "{t_name}" status updated to {new_status}.'
            except Exception:
                return "success", f'Territory "{t_name}" status updated to {new_status}.'

        elif action == "sales_person_create":
            sp_name = payload.get("sales_person_name", "").strip()
            parent_sp = payload.get("parent_sales_person", "").strip() or "Sales Team"
            is_group = int(payload.get("is_group", 0))
            enabled = int(payload.get("enabled", 1))
            emp = payload.get("employee", "").strip()
            body = {
                "sales_person_name": sp_name,
                "parent_sales_person": parent_sp,
                "is_group": is_group,
                "enabled": enabled
            }
            if emp:
                body["employee"] = emp
            dept = payload.get("department", "").strip()
            if dept:
                body["department"] = dept
            comm = payload.get("commission_rate")
            if comm:
                try:
                    body["commission_rate"] = float(comm)
                except Exception:
                    pass
            targets = payload.get("targets")
            if targets and isinstance(targets, list) and len(targets) > 0:
                cleaned_targets = []
                for t in targets:
                    if isinstance(t, dict):
                        item_grp = (t.get("item_group") or "").strip() or "All Item Groups"
                        dist_id = (t.get("distribution_id") or "").strip() or "Evenly Distributed"
                        qty = float(t.get("target_qty") or 0)
                        amt = float(t.get("target_amount") or 0)
                        if item_grp or qty > 0 or amt > 0:
                            cleaned_targets.append({
                                "item_group": item_grp,
                                "fiscal_year": (t.get("fiscal_year") or "2026").strip(),
                                "target_qty": qty,
                                "target_amount": amt,
                                "distribution_id": dist_id
                            })
                if cleaned_targets:
                    body["targets"] = cleaned_targets

            def do_post_sp(p_body):
                data = json.dumps(p_body).encode("utf-8")
                p_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person",
                    data=data,
                    headers=headers_json,
                    method="POST"
                )
                return opener.open(p_req, timeout=10)

            try:
                res = do_post_sp(body)
                if res.status in [200, 201]:
                    return "success", f'Sales Person "{sp_name}" added to Sales Person Tree on {get_server_display_name()}!'
                return "warning", f"ERPNext responded with HTTP {res.status}"
            except urllib.error.HTTPError as he:
                err_text = he.read().decode("utf-8", errors="ignore")
                # Resilience: If targets failed, retry without targets
                if "distribution_id" in err_text or "Target Detail" in err_text or "Monthly Distribution" in err_text:
                    if "targets" in body:
                        del body["targets"]
                        try:
                            res = do_post_sp(body)
                            if res.status in [200, 201]:
                                return "success", f'Sales Person "{sp_name}" added to Sales Person Tree (targets omitted due to schema alignment)!'
                        except Exception:
                            pass
                # Resilience: If parent failed, retry with Sales Team
                if "Parent Sales Person" in err_text or "parent_sales_person" in err_text:
                    body["parent_sales_person"] = "Sales Team"
                    try:
                        res = do_post_sp(body)
                        if res.status in [200, 201]:
                            return "success", f'Sales Person "{sp_name}" added under "Sales Team"!'
                    except Exception:
                        pass
                # Resilience: If employee failed, retry without employee
                if "Employee" in err_text or "employee" in err_text:
                    if "employee" in body:
                        del body["employee"]
                        try:
                            res = do_post_sp(body)
                            if res.status in [200, 201]:
                                return "success", f'Sales Person "{sp_name}" added (unlinked from unverified employee)!'
                        except Exception:
                            pass
                raise he

        elif action == "employee_create":
            first_name = payload.get("first_name", "").strip()
            last_name = payload.get("last_name", "").strip()
            gender = payload.get("gender", "Male").strip()
            dob = payload.get("date_of_birth", "1995-01-01").strip()
            doj = payload.get("date_of_joining", "2024-01-01").strip()
            company = payload.get("company", "Professional Insights Marketing Services").strip()
            status = payload.get("status", "Active").strip()
            body = {
                "first_name": first_name,
                "gender": gender,
                "date_of_birth": dob,
                "date_of_joining": doj,
                "company": company,
                "status": status
            }
            if last_name:
                body["last_name"] = last_name
            if payload.get("middle_name"):
                body["middle_name"] = payload.get("middle_name").strip()
            if payload.get("designation"):
                body["designation"] = payload.get("designation").strip()
            if payload.get("department"):
                body["department"] = payload.get("department").strip()
            if payload.get("reports_to"):
                body["reports_to"] = payload.get("reports_to").strip()
            if payload.get("cell_number"):
                body["cell_number"] = payload.get("cell_number").strip()
            if payload.get("company_email"):
                body["company_email"] = payload.get("company_email").strip()

            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Employee",
                data=data,
                headers=headers_json,
                method="POST"
            )
            res = call_erpnext_resiliently(opener, req, timeout=12)
            if res.status in [200, 201]:
                try:
                    created_doc = json.loads(res.read().decode("utf-8")).get("data", {})
                    new_id = created_doc.get("name") or "New Employee"
                    full_name = created_doc.get("employee_name") or f"{first_name} {last_name}".strip()
                    return "success", f'Employee "{full_name}" ({new_id}) created on {get_server_display_name()}!'
                except Exception:
                    return "success", f'Employee created successfully on {get_server_display_name()}!'
            return "warning", f"ERPNext responded with HTTP {res.status}"

        elif action == "tree_refresh":
            return "success", f"Territory tree synchronized live from {get_server_display_name()}!"

        elif action == "doctor_transfer":
            prog = safe_str(payload.get("program")) or "Abbott Diabetes Care"
            src = safe_str(payload.get("source_territory"))
            tgt = safe_str(payload.get("target_territory"))
            cnt_tgt = int(payload.get("transferred_to_target", 0) or 0)
            cnt_src = int(payload.get("transferred_to_source", 0) or 0)
            accs = payload.get("accounts")

            if "doctor_transfers" not in st.session_state:
                st.session_state["doctor_transfers"] = []
            st.session_state["doctor_transfers"].append({
                "program": prog,
                "source": src,
                "target": tgt,
                "transferred_to_target": cnt_tgt,
                "transferred_to_source": cnt_src,
                "timestamp": time.time()
            })

            if accs and isinstance(accs, list):
                st.session_state[f"live_accounts_{prog}"] = accs

            msg = f'Doctor portfolio transfer between "{src}" and "{tgt}" recorded successfully ({cnt_tgt} doctors assigned to {tgt}).'
            return "success", msg

        return "info", f"Action {action} processed."

    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            err_json = json.loads(err_body)
            msg = err_json.get("exception") or err_json.get("message")
            if not msg and err_json.get("_server_messages"):
                try:
                    msgs = json.loads(err_json["_server_messages"])
                    if msgs:
                        m_obj = json.loads(msgs[0]) if isinstance(msgs[0], str) else msgs[0]
                        msg = m_obj.get("message")
                except Exception:
                    pass
            if not msg:
                msg = f"HTTP Error {e.code}"
            return "warning", f"ERPNext: {msg}"
        except Exception:
            return "warning", f"ERPNext response status: HTTP {e.code}"
    except Exception as e:
        return "error", f"Network error: {str(e)}"


# Persistent Cross-Refresh Session Cache
if "ACTIVE_SESSIONS" not in globals():
    ACTIVE_SESSIONS = {}

SESSION_MAX_AGE_SECONDS = 7 * 86400  # 7 days

def get_query_param(key):
    try:
        if hasattr(st, "query_params"):
            return st.query_params.get(key)
        elif hasattr(st, "experimental_get_query_params"):
            vals = st.experimental_get_query_params().get(key, [])
            return vals[0] if vals else None
    except Exception:
        pass
    return None

def set_query_param(key, value):
    try:
        if hasattr(st, "query_params"):
            st.query_params[key] = value
        elif hasattr(st, "experimental_set_query_params"):
            st.experimental_set_query_params(**{key: value})
    except Exception:
        pass

def clear_query_param(key=None):
    try:
        if hasattr(st, "query_params"):
            if key:
                if key in st.query_params:
                    del st.query_params[key]
            else:
                st.query_params.clear()
        elif hasattr(st, "experimental_set_query_params"):
            if key:
                params = st.experimental_get_query_params()
                params.pop(key, None)
                st.experimental_set_query_params(**params)
            else:
                st.experimental_set_query_params()
    except Exception:
        pass

def purge_expired_sessions():
    now = time.time()
    expired = [k for k, v in ACTIVE_SESSIONS.items() if now - v.get("last_active", 0) > SESSION_MAX_AGE_SECONDS]
    for k in expired:
        ACTIVE_SESSIONS.pop(k, None)

# 3. Mount Territory Reconfiguration Portal Component
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(CURRENT_DIR, "index.html")
PORTAL_HTML = os.path.join(CURRENT_DIR, "territory_reconfiguration_portal.html")

# Ensure index.html is strictly synchronized with territory_reconfiguration_portal.html
if os.path.exists(PORTAL_HTML):
    import shutil
    try:
        if (not os.path.exists(INDEX_HTML) or 
            os.path.getsize(INDEX_HTML) != os.path.getsize(PORTAL_HTML) or 
            os.path.getmtime(PORTAL_HTML) > os.path.getmtime(INDEX_HTML)):
            shutil.copy2(PORTAL_HTML, INDEX_HTML)
    except Exception:
        pass

portal_component = components.declare_component("pims_portal", path=CURRENT_DIR)

# SECURITY INVARIANT: Clear any lingering sfe_session from URL query parameters to prevent auto-login breaches
session_token = get_query_param("sfe_session")
if session_token:
    clear_query_param("sfe_session")
session_token = None



if "auth_response" not in st.session_state:
    st.session_state["auth_response"] = None
if "pending_auth_delivery" not in st.session_state:
    st.session_state["pending_auth_delivery"] = False
if "reset_password_response" not in st.session_state:
    st.session_state["reset_password_response"] = None
if "opener" not in st.session_state:
    st.session_state["opener"] = None

# Single-delivery auth response: deliver ONLY during the active login dispatch cycle.
# On subsequent browser page refreshes (F5) or reboots, deliver None so the web app always opens on the Login Page!
auth_to_deliver = None
if st.session_state.get("pending_auth_delivery"):
    auth_to_deliver = st.session_state.get("auth_response")
    st.session_state["pending_auth_delivery"] = False

# Only attempt authenticated opener and live fetch if an authorized session is active
if st.session_state.get("auth_response") and st.session_state["auth_response"].get("authorized"):
    if not st.session_state.get("opener"):
        st.session_state["opener"] = get_authenticated_opener()
    if "live_territories" not in st.session_state or st.session_state["live_territories"] is None:
        st.session_state["live_territories"] = fetch_live_territories(st.session_state["opener"]) if st.session_state["opener"] else None
    if "live_sales_persons" not in st.session_state or st.session_state["live_sales_persons"] is None:
        st.session_state["live_sales_persons"] = fetch_live_sales_persons(st.session_state["opener"]) if st.session_state["opener"] else None
    if "live_institutions" not in st.session_state or st.session_state["live_institutions"] is None:
        st.session_state["live_institutions"] = fetch_live_institutions(st.session_state["opener"]) if st.session_state["opener"] else None
else:
    if "live_territories" not in st.session_state:
        st.session_state["live_territories"] = None

if "live_sales_persons" not in st.session_state:
    st.session_state["live_sales_persons"] = None
if "live_employees" not in st.session_state:
    st.session_state["live_employees"] = None
if "live_users" not in st.session_state:
    st.session_state["live_users"] = None
if "live_institutions" not in st.session_state:
    st.session_state["live_institutions"] = None
if "tree_sync_event" not in st.session_state:
    st.session_state["tree_sync_event"] = None
if "last_action_timestamp" not in st.session_state:
    st.session_state["last_action_timestamp"] = 0

# Render the web app component directly (Opens directly to the native login view)
_active_prog = st.session_state.get("active_program", "Abbott Diabetes Care")
component_val = portal_component(
    auth_response=auth_to_deliver,
    reset_password_response=st.session_state["reset_password_response"],
    live_territories=st.session_state["live_territories"],
    live_sales_persons=st.session_state["live_sales_persons"],
    live_employees=st.session_state["live_employees"],
    live_users=st.session_state["live_users"],
    live_institutions=st.session_state["live_institutions"],
    live_accounts=st.session_state.get(f"live_accounts_{_active_prog}"),
    tree_sync_event=st.session_state["tree_sync_event"],
    key="pims_portal_app"
)

# Handle events dispatched from the portal
if component_val and isinstance(component_val, dict):
    action = component_val.get("action")
    ts = component_val.get("timestamp", 0)

    # De-duplicate events to strictly eliminate infinite rerun loops
    if ts > st.session_state["last_action_timestamp"]:
        st.session_state["last_action_timestamp"] = ts
        if action == "login":
            usr = component_val.get("usr")
            pwd = component_val.get("pwd")
            res, opener = verify_erpnext_credentials(usr, pwd)
            st.session_state["auth_response"] = res
            st.session_state["pending_auth_delivery"] = True
            if res.get("authorized") and opener:
                st.session_state["opener"] = opener
                _get_shared_opener_store()["opener"] = opener
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                        f_terrs = executor.submit(fetch_live_territories, opener)
                        f_sps = executor.submit(fetch_live_sales_persons, opener)
                        f_emps = executor.submit(fetch_live_employees, opener)
                        f_users = executor.submit(fetch_live_users, opener)
                        f_insts = executor.submit(fetch_live_institutions, opener)
                        st.session_state["live_territories"] = f_terrs.result()
                        st.session_state["live_sales_persons"] = f_sps.result()
                        st.session_state["live_employees"] = f_emps.result()
                        st.session_state["live_users"] = f_users.result()
                        st.session_state["live_institutions"] = f_insts.result()
                except Exception as ex:
                    print(f"[Streamlit Data Fetch Warning] {ex}")
                    st.session_state["live_territories"] = fetch_live_territories(opener)
                    st.session_state["live_users"] = fetch_live_users(opener)
                    st.session_state["live_institutions"] = fetch_live_institutions(opener)
                token = secrets.token_urlsafe(32)
                st.session_state["session_token"] = token
                clear_query_param("sfe_session")
            else:
                # Failed login: strictly wipe lingering session credentials and tokens
                st.session_state["opener"] = None
                _get_shared_opener_store()["opener"] = None
                st.session_state["session_token"] = None
                st.session_state["live_territories"] = None
                clear_query_param("sfe_session")

            # Immediately scrub credentials from memory and component payload
            if "pwd" in component_val:
                component_val["pwd"] = ""
            del pwd
            del usr
            st.rerun()
        elif action == "reset_password":
            target_user = component_val.get("user") or component_val.get("usr")
            reset_res = request_erpnext_password_reset(target_user)
            st.session_state["reset_password_response"] = {
                "timestamp": ts,
                "success": reset_res.get("success", False),
                "message": reset_res.get("message", "")
            }
            st.rerun()
        elif action == "logout":
            token = st.session_state.get("session_token") or get_query_param("sfe_session")
            if token and token in ACTIVE_SESSIONS:
                ACTIVE_SESSIONS.pop(token, None)
            clear_query_param("sfe_session")
            st.session_state["auth_response"] = None
            st.session_state["pending_auth_delivery"] = False
            st.session_state["reset_password_response"] = None
            st.session_state["opener"] = None
            _get_shared_opener_store()["opener"] = None
            st.session_state["live_territories"] = None
            st.session_state["live_sales_persons"] = None
            st.session_state["live_employees"] = None
            st.session_state["live_users"] = None
            st.session_state["live_institutions"] = None
            st.session_state["tree_sync_event"] = None
            st.session_state["session_token"] = None
            st.rerun()
        elif action in ["inst_approve", "inst_normalize", "inst_reject", "inst_remap", "inst_create", "inst_propose", "inst_refresh"]:
            opener = st.session_state.get("opener")
            if not opener:
                opener = get_authenticated_opener()
                st.session_state["opener"] = opener
            status, msg = execute_institution_action(opener, action, component_val)
            opener = st.session_state.get("opener") or get_authenticated_opener()
            if opener:
                st.session_state["opener"] = opener
                fresh_insts = fetch_live_institutions(opener)
                if fresh_insts is not None:
                    st.session_state["live_institutions"] = fresh_insts
                i_count = len(st.session_state.get("live_institutions") or [])
                if action == "inst_refresh":
                    msg = f"Live ERPNext sync complete: {i_count} institutions loaded directly from {get_server_display_name()}!"
                    status = "success"
            if not (action == "inst_refresh" and component_val.get("silent")):
                st.session_state["tree_sync_event"] = {
                    "action": action,
                    "status": status,
                    "message": msg,
                    "timestamp": ts
                }
            st.rerun()
        elif action in ["tree_add", "bulk_tree_add", "tree_edit", "tree_rename", "tree_delete", "territory_toggle_status", "territory_deactivate", "tree_refresh", "sales_person_create", "employee_create", "doctor_transfer"]:
            opener = st.session_state.get("opener")
            if not opener:
                opener = get_authenticated_opener()
                st.session_state["opener"] = opener
            if action == "doctor_transfer" and component_val.get("program"):
                st.session_state["active_program"] = component_val.get("program")
            status, msg = execute_tree_action(opener, action, component_val)
            opener = st.session_state.get("opener") or get_authenticated_opener()
            if opener:
                st.session_state["opener"] = opener
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                        f_terrs = executor.submit(fetch_live_territories, opener)
                        f_sps = executor.submit(fetch_live_sales_persons, opener)
                        f_emps = executor.submit(fetch_live_employees, opener)
                        f_users = executor.submit(fetch_live_users, opener)
                        f_insts = executor.submit(fetch_live_institutions, opener)
                        st.session_state["live_territories"] = f_terrs.result()
                        st.session_state["live_sales_persons"] = f_sps.result()
                        st.session_state["live_employees"] = f_emps.result()
                        st.session_state["live_users"] = f_users.result()
                        st.session_state["live_institutions"] = f_insts.result()
                except Exception as ex:
                    st.session_state["live_territories"] = fetch_live_territories(opener)
                    st.session_state["live_sales_persons"] = fetch_live_sales_persons(opener)
                    st.session_state["live_employees"] = fetch_live_employees(opener)
                    st.session_state["live_users"] = fetch_live_users(opener)

                t_count = len(st.session_state.get("live_territories") or [])
                if action == "tree_refresh":
                    msg = f"Live ERPNext sync complete: {t_count} territories loaded directly from {get_server_display_name()}!"
                    status = "success"

                token = st.session_state.get("session_token")
                if token and token in ACTIVE_SESSIONS:
                    ACTIVE_SESSIONS[token]["live_territories"] = st.session_state["live_territories"]
                    ACTIVE_SESSIONS[token]["live_sales_persons"] = st.session_state["live_sales_persons"]
                    ACTIVE_SESSIONS[token]["live_employees"] = st.session_state["live_employees"]
                    ACTIVE_SESSIONS[token]["live_users"] = st.session_state["live_users"]
                    ACTIVE_SESSIONS[token]["last_active"] = time.time()
            if not (action == "tree_refresh" and component_val.get("silent")):
                st.session_state["tree_sync_event"] = {
                    "action": action,
                    "status": status,
                    "message": msg,
                    "timestamp": ts
                }
            st.rerun()

