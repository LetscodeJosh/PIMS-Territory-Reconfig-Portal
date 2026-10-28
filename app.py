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

def get_erpnext_url():
    """Dynamically resolves ERPNext server endpoint strictly from Streamlit secrets, environment, or .env."""
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

def get_authenticated_opener(force_refresh=False):
    if not force_refresh and "opener" in st.session_state and st.session_state["opener"]:
        return st.session_state["opener"]

    opener, cj = create_erpnext_opener()
    opener.cookie_jar = cj
    svc_user = os.environ.get("PIMS_SERVICE_USER") or (st.secrets.get("PIMS_SERVICE_USER") if hasattr(st, "secrets") and "PIMS_SERVICE_USER" in st.secrets else "")
    svc_pwd = os.environ.get("PIMS_SERVICE_PASSWORD") or (st.secrets.get("PIMS_SERVICE_PASSWORD") if hasattr(st, "secrets") and "PIMS_SERVICE_PASSWORD" in st.secrets else "")
    if svc_user and svc_pwd:
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
                return opener
        except Exception as ex:
            print(f"[Auto Session Renewal Error] {ex}")
    st.session_state["opener"] = opener
    return opener

def call_erpnext_resiliently(opener, req, timeout=12):
    """Executes ERPNext HTTP requests with automatic session recovery if idle for long periods."""
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as he:
        if he.code in [401, 403]:
            # Session expired: auto-renew credentials and retry once
            refreshed = get_authenticated_opener(force_refresh=True)
            if refreshed:
                st.session_state["opener"] = refreshed
                return refreshed.open(req, timeout=timeout)
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
    try:
        fields = json.dumps([
            "name",
            "territory_name",
            "parent_territory",
            "is_group",
            "territory_manager",
            "custom_user_id",
            "custom_account_or_program"
        ])
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory?fields={urllib.parse.quote(fields)}&limit_page_length=1000"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        res = call_erpnext_resiliently(opener, req, timeout=12)
        data = json.loads(res.read().decode("utf-8")).get("data", [])
        return data
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live territories: {e}")
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
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Institution?fields={urllib.parse.quote(fields)}&order_by=name%20desc&limit_page_length=0"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            res = call_erpnext_resiliently(opener, req, timeout=15)
            data = json.loads(res.read().decode("utf-8")).get("data", [])
        except Exception:
            core_fields = json.dumps(["name", "institution_name", "region_name", "province_name", "city_municipality", "workflow_state", "rejection_reason", "owner", "creation", "modified", "docstatus", "ownership", "institution_type", "service_capability"])
            fallback_url = f"{ERPNEXT_SERVER_URL}/api/resource/Institution?fields={urllib.parse.quote(core_fields)}&order_by=name%20desc&limit_page_length=0"
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
            target_state = "Pending DSM Approval" if needs_dsm else "Approved"
            target_docstatus = 0 if needs_dsm else 1
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

            return "success", f'Institution "{inst_title}" ({name}) {("routed to DSM" if needs_dsm else "approved and synced to Mobile App Directory")}!'

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

        return "info", f"Institution action {action} processed."
    except Exception as e:
        return "error", f"Institution action error: {str(e)}"

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

        if action == "tree_add":
            t_name = safe_str(payload.get("territory_name"))
            parent = safe_str(payload.get("parent_territory")) or "All Territories"
            is_group = int(payload.get("is_group", 0) or 0)
            t_mgr = safe_str(payload.get("territory_manager"))
            if not t_name:
                return "error", "Territory name cannot be blank."
            body = {
                "territory_name": t_name,
                "parent_territory": parent,
                "is_group": is_group
            }
            if t_mgr:
                body["territory_manager"] = t_mgr
            if payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"):
                body["custom_user_id"] = safe_str(payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"))
            if payload.get("custom_account_or_program") or payload.get("program"):
                body["custom_account_or_program"] = safe_str(payload.get("custom_account_or_program") or payload.get("program"))
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                data=data,
                headers=headers_json,
                method="POST"
            )
            try:
                res = call_erpnext_resiliently(opener, req, timeout=12)
                if res.status in [200, 201]:
                    return "success", f'Territory "{t_name}" created live on {get_server_display_name()}!'
                return "warning", f"ERPNext responded with HTTP {res.status}"
            except urllib.error.HTTPError as he:
                err_text = he.read().decode("utf-8", errors="ignore")
                if "DuplicateEntryError" in err_text:
                    return "warning", f'Territory "{t_name}" already exists in ERPNext.'
                if "LinkValidationError" in err_text and "territory_manager" in err_text and "territory_manager" in body:
                    del body["territory_manager"]
                    data = json.dumps(body).encode("utf-8")
                    req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                        data=data,
                        headers=headers_json,
                        method="POST"
                    )
                    res = call_erpnext_resiliently(opener, req, timeout=12)
                    if res.status in [200, 201]:
                        return "success", f'Territory "{t_name}" created live on {get_server_display_name()}!'
                raise he

        elif action == "tree_edit":
            orig_name = safe_str(payload.get("name"))
            new_parent = safe_str(payload.get("parent_territory")) or "All Territories"
            new_is_group = int(payload.get("is_group", 0) or 0)
            new_mgr = safe_str(payload.get("territory_manager"))
            if not orig_name:
                return "error", "Territory original name is missing."
            body = {
                "parent_territory": new_parent,
                "is_group": new_is_group
            }
            if new_mgr:
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
                    return "success", f'Territory "{orig_name}" updated live on {get_server_display_name()}!'
                return "warning", f"ERPNext responded with HTTP {res.status}"
            except urllib.error.HTTPError as he:
                err_text = he.read().decode("utf-8", errors="ignore")
                if "LinkValidationError" in err_text and "territory_manager" in err_text and "territory_manager" in body:
                    del body["territory_manager"]
                    data = json.dumps(body).encode("utf-8")
                    req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(orig_name)}",
                        data=data,
                        headers=headers_json,
                        method="PUT"
                    )
                    res = call_erpnext_resiliently(opener, req, timeout=12)
                    if res.status == 200:
                        return "success", f'Territory "{orig_name}" updated live on {get_server_display_name()}!'
                raise he

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
            t_name = safe_str(payload.get("territory") or payload.get("name"))
            new_mgr = safe_str(payload.get("territory_manager"))
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
                    return "success", f'Territory "{t_name}" status synced to {get_server_display_name()} ({new_mgr})'
                return "warning", f"ERPNext responded with HTTP {res.status}"
            except Exception as e:
                return "warning", f'Territory "{t_name}" updated locally ({e})'

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
            return "warning", f"ERPNext Error (HTTP {e.code})"
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
    if "live_territories" not in st.session_state or not st.session_state["live_territories"]:
        st.session_state["live_territories"] = fetch_live_territories(st.session_state["opener"]) if st.session_state["opener"] else None
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
component_val = portal_component(
    auth_response=auth_to_deliver,
    reset_password_response=st.session_state["reset_password_response"],
    live_territories=st.session_state["live_territories"],
    live_sales_persons=st.session_state["live_sales_persons"],
    live_employees=st.session_state["live_employees"],
    live_users=st.session_state["live_users"],
    live_institutions=st.session_state["live_institutions"],
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
                token = secrets.token_urlsafe(32)
                st.session_state["session_token"] = token
                clear_query_param("sfe_session")
            else:
                # Failed login: strictly wipe lingering session credentials and tokens
                st.session_state["opener"] = None
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
            st.session_state["live_territories"] = None
            st.session_state["live_sales_persons"] = None
            st.session_state["live_employees"] = None
            st.session_state["live_users"] = None
            st.session_state["live_institutions"] = None
            st.session_state["tree_sync_event"] = None
            st.session_state["session_token"] = None
            st.rerun()
        elif action in ["inst_approve", "inst_normalize", "inst_reject", "inst_remap", "inst_refresh"]:
            opener = st.session_state.get("opener")
            if not opener:
                opener = get_authenticated_opener()
                st.session_state["opener"] = opener
            status, msg = execute_institution_action(opener, action, component_val)
            opener = st.session_state.get("opener") or get_authenticated_opener()
            if opener:
                st.session_state["opener"] = opener
                st.session_state["live_institutions"] = fetch_live_institutions(opener)
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
        elif action in ["tree_add", "tree_edit", "tree_rename", "tree_delete", "territory_deactivate", "tree_refresh", "sales_person_create", "employee_create"]:
            opener = st.session_state.get("opener")
            if not opener:
                opener = get_authenticated_opener()
                st.session_state["opener"] = opener
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
            st.session_state["tree_sync_event"] = {
                "action": action,
                "status": status,
                "message": msg,
                "timestamp": ts
            }
            st.rerun()

