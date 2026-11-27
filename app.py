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

# Live ERPNext Authoritative Mode: Do NOT persist or re-inject temporary Institution records from local JSON.
APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_INST_FILE = os.path.join(APP_BASE_DIR, "shared_institution_state.json")

def load_shared_inst_overrides():
    return {}

def save_shared_inst_override(inst_id, override_data):
    # Intentionally disabled: ERPNext Staging Institution DocType is the sole source of truth.
    return

# Live ERPNext Authoritative Mode: Do NOT persist or re-inject temporary Territory or Sales Person records from local JSON.
SHARED_TERRITORY_FILE = os.path.join(APP_BASE_DIR, "shared_territory_state.json")

def load_shared_territory_state():
    return {"territories": {}, "renames": {}, "deleted": [], "overrides": {}, "sales_persons": {}, "sp_renames": {}}

def save_shared_territory_state(state):
    # Intentionally disabled: ERPNext DocTypes are the sole source of truth (no temporary JSON caching).
    return

def record_shared_territory_add(name, parent, is_group, manager="", user_id="", program="", district="", pending_erp_sync=False):
    return

def record_shared_territory_edit(orig_name, parent=None, is_group=None, manager=None, user_id=None, program=None, status=None, district=None, pending_erp_sync=None):
    return

def record_shared_sales_person_meta(sp_name, parent_sp=None, is_group=None, district=None, program=None, employee=None, pending_erp_sync=False):
    return

def _replace_parenthesized_territory_code(sp_name, old_code, new_code):
    """Replaces only an exact parenthesized territory code token (e.g. 'ARCENE PIANG (AD0116)' -> 'ARCENE PIANG (AD0900)')."""
    clean_sp = safe_str(sp_name)
    clean_old = safe_str(old_code)
    clean_new = safe_str(new_code)
    if not clean_sp or not clean_old or not clean_new:
        return None
    if clean_old.lower() == clean_new.lower():
        return None
    pattern = re.compile(r"\(\s*" + re.escape(clean_old) + r"\s*\)", re.IGNORECASE)
    if not pattern.search(clean_sp):
        return None
    return pattern.sub(lambda _m: f"({clean_new})", clean_sp)

def record_shared_sales_person_rename(old_sp_name, new_sp_name):
    return

def merge_shared_sales_persons_into_list(sp_list, is_live_erpnext=False):
    if not isinstance(sp_list, list):
        return []
    normalized = []
    seen = set()
    for s in sp_list:
        if not isinstance(s, dict):
            continue
        sp_copy = dict(s)
        eff_name = safe_str(sp_copy.get("name") or sp_copy.get("sales_person_name"))
        if not eff_name:
            continue
        key = eff_name.lower()
        if key in seen:
            continue
        seen.add(key)
        if safe_str(sp_copy.get("custom_district")) and not safe_str(sp_copy.get("district")):
            sp_copy["district"] = sp_copy["custom_district"]
        normalized.append(sp_copy)
    return normalized

def record_shared_territory_rename(old_name, new_name):
    return

def record_shared_territory_deletion(name):
    return

def merge_shared_territories_into_list(terrs_list, is_live_erpnext=False):
    if not isinstance(terrs_list, list):
        return []
    normalized = []
    seen = set()
    for orig_t in terrs_list:
        if not isinstance(orig_t, dict):
            continue
        t = dict(orig_t)
        name = safe_str(t.get("name") or t.get("territory_name"))
        if not name or name in seen:
            continue
        if safe_str(t.get("custom_district")) and not safe_str(t.get("district")):
            t["district"] = t["custom_district"]
        seen.add(name)
        normalized.append(t)
    return normalized

def get_erpnext_url():
    """Dynamically resolves ERPNext server endpoint strictly targeting Staging (https://staging.pmii-marketing.com)."""
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
    return "https://staging.pmii-marketing.com"

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

def _opener_has_valid_sid(op):
    if not op:
        return False
    jar = getattr(op, "cookie_jar", None)
    if jar is None:
        return True
    try:
        return any(c.name == "sid" and c.value and c.value != "Guest" for c in jar)
    except Exception:
        return False

def get_authenticated_opener(force_refresh=False):
    existing_opener = None
    try:
        if "opener" in st.session_state and st.session_state["opener"]:
            existing_opener = st.session_state["opener"]
    except Exception:
        existing_opener = None
    if not existing_opener:
        try:
            shared = _get_shared_opener_store().get("opener")
            if shared:
                existing_opener = shared
                try:
                    st.session_state["opener"] = existing_opener
                except Exception:
                    pass
        except Exception:
            pass

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
            has_sid = any(c.name == "sid" and c.value and c.value != "Guest" for c in cj)
            if res_data.get("message") == "Logged In" and has_sid:
                try:
                    st.session_state["opener"] = opener
                except Exception:
                    pass
                try:
                    _get_shared_opener_store()["opener"] = opener
                except Exception:
                    pass
                return opener
        except Exception as ex:
            print(f"[Auto Session Renewal Error] {ex}")

    if existing_opener and not force_refresh:
        return existing_opener

    return None

def _get_frappe_csrf_token(opener, force_refresh=False):
    """Safely retrieves and caches the Frappe CSRF token for cookie-authenticated POST/PUT/DELETE calls."""
    if not opener:
        return ""
    cached = getattr(opener, "_frappe_csrf_token", "")
    if cached and not force_refresh:
        return cached
    token = ""
    try:
        req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/method/frappe.sessions.get_csrf_token",
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        res = opener.open(req, timeout=6)
        raw = res.read().decode("utf-8", errors="ignore")
        parsed = json.loads(raw) if raw else {}
        val = parsed.get("message") if isinstance(parsed, dict) else ""
        if isinstance(val, str) and val.strip():
            token = val.strip()
    except Exception:
        pass
    if not token:
        try:
            app_req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/app",
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"}
            )
            app_res = opener.open(app_req, timeout=6)
            html = app_res.read().decode("utf-8", errors="ignore")
            m = re.search(r'(?:frappe\.csrf_token|window\.csrf_token)\s*=\s*["\']([A-Za-z0-9_\-\.]+)["\']', html)
            if m:
                token = m.group(1).strip()
        except Exception:
            pass
    try:
        setattr(opener, "_frappe_csrf_token", token)
    except Exception:
        pass
    return token


def _clone_request_with_headers(req, extra_headers=None, strip_cookie=False):
    headers = {}
    for k, v in req.header_items():
        if strip_cookie and k.lower() == "cookie":
            continue
        headers[k] = v
    if extra_headers:
        for ek, ev in extra_headers.items():
            if ev is not None:
                headers[ek] = ev
    return urllib.request.Request(
        req.full_url,
        data=req.data,
        headers=headers,
        method=req.get_method()
    )


def call_erpnext_resiliently(opener, req, timeout=12):
    """Executes ERPNext HTTP requests with Frappe CSRF support and automatic 401 session recovery without clobbering on 403."""
    method = (req.get_method() or "GET").upper()
    active_req = req
    if method in ("POST", "PUT", "DELETE", "PATCH"):
        existing_lower = {k.lower() for k, _ in req.header_items()}
        extra = {}
        if "expect" not in existing_lower:
            extra["Expect"] = ""
        if "x-frappe-csrf-token" not in existing_lower:
            csrf_tok = _get_frappe_csrf_token(opener, force_refresh=False)
            if csrf_tok:
                extra["X-Frappe-CSRF-Token"] = csrf_tok
        if extra:
            active_req = _clone_request_with_headers(req, extra_headers=extra, strip_cookie=False)
    try:
        return opener.open(active_req, timeout=timeout)
    except urllib.error.HTTPError as he:
        if he.code in (400, 403) and method in ("POST", "PUT", "DELETE", "PATCH"):
            err_preview = ""
            try:
                err_bytes = he.read()
                err_preview = err_bytes.decode("utf-8", errors="ignore")
                import io
                err_buf = io.BytesIO(err_bytes)
                he.fp = err_buf
                he.read = err_buf.read
            except Exception:
                pass
            low_preview = err_preview.lower()
            if "csrf" in low_preview or "invalid request" in low_preview:
                fresh_csrf = _get_frappe_csrf_token(opener, force_refresh=True)
                if fresh_csrf:
                    retry_csrf_req = _clone_request_with_headers(
                        req,
                        extra_headers={"X-Frappe-CSRF-Token": fresh_csrf, "Expect": ""},
                        strip_cookie=True
                    )
                    return opener.open(retry_csrf_req, timeout=timeout)
        if he.code == 401:
            refreshed = get_authenticated_opener(force_refresh=True)
            if refreshed and refreshed is not opener and _opener_has_valid_sid(refreshed):
                try:
                    st.session_state["opener"] = refreshed
                except Exception:
                    pass
                extra_retry = {}
                if method in ("POST", "PUT", "DELETE", "PATCH"):
                    extra_retry["Expect"] = ""
                    csrf_tok = _get_frappe_csrf_token(refreshed, force_refresh=True)
                    if csrf_tok:
                        extra_retry["X-Frappe-CSRF-Token"] = csrf_tok
                retry_req = _clone_request_with_headers(req, extra_headers=extra_retry, strip_cookie=True)
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
    opener.cookie_jar = cj
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

MAX_LOGIN_ATTEMPTS = 6
LOGIN_COOLDOWN_SECONDS = 5 * 60

@st.cache_resource
def _get_security_rate_limit_store():
    return {
        "reset_requests": {},
        "login_attempts": {}
    }

_SECURITY_STORE = _get_security_rate_limit_store()
STREAMLIT_RESET_REQUESTS = _SECURITY_STORE["reset_requests"]
STREAMLIT_LOGIN_ATTEMPTS = _SECURITY_STORE["login_attempts"]

def _extract_frappe_error_message(raw_body, fallback_msg):
    """Extract a human-readable error message from a Frappe JSON/HTTP error response."""
    if not raw_body:
        return fallback_msg
    try:
        err_data = json.loads(raw_body)
        if isinstance(err_data, dict):
            if err_data.get("_server_messages"):
                msgs = json.loads(err_data["_server_messages"])
                if isinstance(msgs, list) and msgs:
                    first = msgs[0]
                    parsed = json.loads(first) if isinstance(first, str) and first.startswith("{") else {"message": str(first)}
                    clean_m = re.sub(r"<[^>]+>", "", str(parsed.get("message") or parsed)).strip()
                    if clean_m:
                        return clean_m
            if err_data.get("message"):
                return re.sub(r"<[^>]+>", "", str(err_data["message"])).strip()
            if err_data.get("exception"):
                return str(err_data["exception"]).splitlines()[-1].strip()
    except Exception:
        pass
    return fallback_msg


def _resolve_reset_user_email(clean_user):
    """Resolve an ERPNext username to its login email when '@' is omitted."""
    if "@" in clean_user:
        return clean_user
    try:
        opener = get_authenticated_opener()
        if not opener:
            return clean_user
        for field in ("username", "name"):
            filters = urllib.parse.quote(json.dumps([["User", field, "=", clean_user]]))
            fields = urllib.parse.quote(json.dumps(["name", "email"]))
            url = f"{ERPNEXT_SERVER_URL}/api/resource/User?filters={filters}&fields={fields}&limit_page_length=1"
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=8) as res:
                data = json.loads(res.read().decode("utf-8")).get("data", [])
                if data and isinstance(data, list):
                    resolved = (data[0].get("email") or data[0].get("name") or "").strip()
                    if resolved:
                        return resolved
    except Exception:
        pass
    return clean_user


def request_erpnext_password_reset(user_email):
    """
    Safely validates and dispatches a password reset link email via ERPNext's
    /api/method/frappe.core.doctype.user.user.reset_password endpoint.
    """
    if not user_email or not isinstance(user_email, str):
        return {
            "success": False,
            "message": "ERPNext email address or username is required."
        }

    clean_user = user_email.strip()
    if not clean_user:
        return {
            "success": False,
            "message": "ERPNext email address or username is required."
        }

    if INJECTION_PATTERN.search(clean_user):
        return {
            "success": False,
            "message": "SECURITY VIOLATION: Malicious command injection or forbidden characters detected in reset request."
        }

    ident = clean_user.lower()
    target_email = _resolve_reset_user_email(clean_user)
    target_ident = target_email.lower()
    rec_ident = STREAMLIT_LOGIN_ATTEMPTS.get(ident, (0, 0))
    rec_target = STREAMLIT_LOGIN_ATTEMPTS.get(target_ident, (0, 0))
    max_failed = max(
        int(rec_ident[0] or 0),
        int(rec_target[0] or 0),
        _get_session_failed_attempts(ident),
        _get_session_failed_attempts(target_ident),
    )
    if max_failed < MAX_LOGIN_ATTEMPTS:
        return {
            "success": False,
            "message": f"Password reset is only permitted after {MAX_LOGIN_ATTEMPTS} failed login attempts for '{clean_user}'."
        }

    # Rate limiting: max 3 requests per 15 minutes
    now = time.time()
    req_record = STREAMLIT_RESET_REQUESTS.get(ident, (0, 0))
    count, reset_window = req_record
    if now < reset_window:
        if count >= 3:
            return {
                "success": False,
                "message": "Rate Limit Exceeded: Maximum 3 password reset requests per 15 minutes. Please contact your System Administrator."
            }
        STREAMLIT_RESET_REQUESTS[ident] = (count + 1, reset_window)
    else:
        STREAMLIT_RESET_REQUESTS[ident] = (1, now + 15 * 60)

    reset_url = f"{ERPNEXT_SERVER_URL}/api/method/frappe.core.doctype.user.user.reset_password"
    payload = urllib.parse.urlencode({"user": target_email}).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PIMS-Streamlit-Client"
    }

    opener, _ = create_erpnext_opener()
    for attempt in range(2):
        try:
            req = urllib.request.Request(reset_url, data=payload, headers=headers)
            with opener.open(req, timeout=12) as res:
                raw_body = res.read().decode("utf-8", errors="replace")
                res_data = json.loads(raw_body) if raw_body else {}
                msg_val = str(res_data.get("message", "") if isinstance(res_data, dict) else res_data).strip()
                msg_lower = msg_val.lower()
                if msg_lower == "not found" or "not found" in msg_lower or "no user" in raw_body.lower():
                    return {
                        "success": False,
                        "message": f"No ERPNext account found for '{clean_user}'. Please enter the email address used to log in."
                    }
                if "disabled" in msg_lower:
                    return {
                        "success": False,
                        "message": f"Account '{clean_user}' is disabled in ERPNext. Please contact your System Administrator."
                    }
                STREAMLIT_LOGIN_ATTEMPTS.pop(ident, None)
                STREAMLIT_LOGIN_ATTEMPTS.pop(target_email.lower(), None)
                try:
                    sess_attempts = st.session_state.get("sfe_failed_login_attempts")
                    if isinstance(sess_attempts, dict):
                        sess_attempts.pop(ident, None)
                        sess_attempts.pop(target_email.lower(), None)
                except Exception:
                    pass
                print(f"[SECURITY AUDIT] ERPNext password reset link dispatched for user: '{target_email}'.")
                return {
                    "success": True,
                    "message": f"Password reset link has been sent to '{target_email}'. Please check your email inbox (and spam/junk folder) to reset your password."
                }
        except urllib.error.HTTPError as he:
            if he.code in (401, 403) and attempt == 0:
                auth_opener = get_authenticated_opener()
                if auth_opener:
                    opener = auth_opener
                    continue
            raw_err = ""
            try:
                raw_err = he.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            err_msg = _extract_frappe_error_message(raw_err, f"ERPNext server returned HTTP {he.code}")
            if "not found" in err_msg.lower() or "does not exist" in err_msg.lower():
                err_msg = f"No ERPNext account found for '{clean_user}'. Please enter the email address used to log in."
            return {
                "success": False,
                "message": f"ERPNext Password Reset Error: {err_msg}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Unable to reach ERPNext server ({get_server_display_name()}): {str(e)}"
            }

    return {
        "success": False,
        "message": "Unable to complete password reset request. Please try again."
    }


def _get_session_failed_attempts(ident):
    """Retrieve failed attempt count for ident stored in st.session_state."""
    try:
        store = st.session_state.get("sfe_failed_login_attempts")
        if isinstance(store, dict):
            return int(store.get(ident, 0) or 0)
        if isinstance(store, (int, float)):
            return int(store)
    except Exception:
        pass
    return 0


def _set_session_failed_attempts(ident, count):
    """Persist failed attempt count for ident in st.session_state."""
    try:
        store = st.session_state.get("sfe_failed_login_attempts")
        if not isinstance(store, dict):
            store = {}
            st.session_state["sfe_failed_login_attempts"] = store
        if count <= 0:
            store.pop(ident, None)
        else:
            store[ident] = int(count)
    except Exception:
        pass


def _record_failed_login_attempt(ident, base_count, now, failure_prefix):
    """Increment login attempt counter consistently and return auth error payload."""
    new_count = min(MAX_LOGIN_ATTEMPTS, max(0, int(base_count)) + 1)
    remaining = max(0, MAX_LOGIN_ATTEMPTS - new_count)
    if new_count >= MAX_LOGIN_ATTEMPTS:
        lockout_seconds = LOGIN_COOLDOWN_SECONDS
        mm, ss = divmod(lockout_seconds, 60)
        STREAMLIT_LOGIN_ATTEMPTS[ident] = (new_count, now + lockout_seconds)
        _set_session_failed_attempts(ident, new_count)
        return {
            "success": False,
            "authorized": False,
            "locked_user": ident,
            "failed_attempts": new_count,
            "remaining_attempts": 0,
            "lockout_remaining_seconds": lockout_seconds,
            "message": f"Maximum {MAX_LOGIN_ATTEMPTS} login attempts reached. Cooldown remaining: {mm:02d}:{ss:02d} before you can enter your credentials again."
        }
    STREAMLIT_LOGIN_ATTEMPTS[ident] = (new_count, 0)
    _set_session_failed_attempts(ident, new_count)
    return {
        "success": False,
        "authorized": False,
        "failed_attempts": new_count,
        "remaining_attempts": remaining,
        "message": f"{failure_prefix} Remaining Attempt: {remaining}"
    }


def verify_erpnext_credentials(usr, pwd, client_failed_attempts=0):
    if not usr or not pwd:
        return {
            "success": False,
            "authorized": False,
            "message": "Both username and password are required."
        }, None

    usr = usr.strip()
    ident = usr.lower()

    # Check brute-force lockout across persistent cache store and session state
    now = time.time()
    record = STREAMLIT_LOGIN_ATTEMPTS.get(ident, (0, 0))
    record_count, lockout_until = record
    sess_count = _get_session_failed_attempts(ident)
    if lockout_until > now:
        rem_seconds = max(1, int(round(lockout_until - now)))
        mm, ss = divmod(rem_seconds, 60)
        return {
            "success": False,
            "authorized": False,
            "locked_user": usr,
            "failed_attempts": MAX_LOGIN_ATTEMPTS,
            "remaining_attempts": 0,
            "lockout_remaining_seconds": rem_seconds,
            "message": f"Maximum {MAX_LOGIN_ATTEMPTS} login attempts reached. Cooldown remaining: {mm:02d}:{ss:02d} before you can enter your credentials again."
        }, None
    elif lockout_until > 0 and lockout_until <= now:
        STREAMLIT_LOGIN_ATTEMPTS.pop(ident, None)
        _set_session_failed_attempts(ident, 0)
        record_count = 0
        sess_count = 0
    elif record_count >= MAX_LOGIN_ATTEMPTS:
        STREAMLIT_LOGIN_ATTEMPTS.pop(ident, None)
        _set_session_failed_attempts(ident, 0)
        record_count = 0
        sess_count = 0

    max_prior = MAX_LOGIN_ATTEMPTS - 1
    try:
        client_count = max(0, min(max_prior, int(client_failed_attempts or 0)))
    except (ValueError, TypeError):
        client_count = 0
    base_count = min(max_prior, max(int(record_count or 0), int(sess_count or 0), client_count))

    # Security Intrusion Mitigation: Block SQL / Command / Script Injection Attacks on username
    if INJECTION_PATTERN.search(usr):
        STREAMLIT_LOGIN_ATTEMPTS[ident] = (MAX_LOGIN_ATTEMPTS, now + LOGIN_COOLDOWN_SECONDS)
        _set_session_failed_attempts(ident, MAX_LOGIN_ATTEMPTS)
        mm, ss = divmod(LOGIN_COOLDOWN_SECONDS, 60)
        return {
            "success": False,
            "authorized": False,
            "locked_user": usr,
            "failed_attempts": MAX_LOGIN_ATTEMPTS,
            "remaining_attempts": 0,
            "lockout_remaining_seconds": LOGIN_COOLDOWN_SECONDS,
            "message": "SECURITY VIOLATION: Malicious injection attempt detected in username. Request blocked and access restricted."
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
                return _record_failed_login_attempt(
                    ident,
                    base_count,
                    now,
                    "Invalid username or password. Please verify your ERPNext credentials."
                ), None
            if attempt == max_retries - 1:
                return _record_failed_login_attempt(
                    ident,
                    base_count,
                    now,
                    f"ERPNext authentication error (HTTP {e.code}). Please try again."
                ), None
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
        return _record_failed_login_attempt(
            ident,
            base_count,
            now,
            "Authentication failed on ERPNext."
        ), None

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
    _set_session_failed_attempts(ident, 0)

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
        return []
    for fields_list in [
        ["name", "territory_name", "parent_territory", "is_group", "territory_manager", "custom_user_id", "custom_account_or_program", "custom_district"],
        ["name", "territory_name", "parent_territory", "is_group", "territory_manager", "custom_user_id", "custom_account_or_program"],
        ["name", "territory_name", "parent_territory", "is_group", "territory_manager", "custom_district"],
        ["name", "territory_name", "parent_territory", "is_group", "territory_manager"],
        ["name", "territory_name", "parent_territory", "is_group"]
    ]:
        try:
            fields = json.dumps(fields_list)
            url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory?fields={urllib.parse.quote(fields)}&limit_page_length=2000"
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            res = call_erpnext_resiliently(opener, req, timeout=12)
            data = json.loads(res.read().decode("utf-8")).get("data", [])
            if isinstance(data, list):
                return merge_shared_territories_into_list(data, is_live_erpnext=True)
        except Exception as e:
            print(f"[Streamlit Proxy] fetch_live_territories fallback with {fields_list}: {e}")
            continue
    return []

def fetch_live_sales_persons(opener):
    if not opener:
        return []
    for fields_list in [
        ["name", "sales_person_name", "parent_sales_person", "employee", "is_group", "enabled", "department", "custom_district"],
        ["name", "sales_person_name", "parent_sales_person", "employee", "is_group", "enabled", "custom_district"],
        ["name", "sales_person_name", "parent_sales_person", "employee", "is_group", "enabled", "department"],
        ["name", "sales_person_name", "parent_sales_person", "employee", "is_group", "enabled"],
        ["name", "sales_person_name", "parent_sales_person", "is_group", "enabled"]
    ]:
        try:
            fields = json.dumps(fields_list)
            url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person?fields={urllib.parse.quote(fields)}&order_by=is_group%20desc,name%20asc&limit_page_length=2000"
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            res = call_erpnext_resiliently(opener, req, timeout=12)
            data = json.loads(res.read().decode("utf-8")).get("data", [])
            if isinstance(data, list):
                return merge_shared_sales_persons_into_list(data, is_live_erpnext=True)
        except Exception as e:
            print(f"[Streamlit Proxy] Failed to fetch live sales persons with {fields_list}: {e}")
            continue
    return []

def fetch_live_employees(opener):
    if not opener:
        return []
    try:
        fields = json.dumps(["name", "employee_name", "first_name", "last_name", "gender", "company", "status", "department", "designation", "user_id", "company_email", "personal_email"])
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
            res = call_erpnext_resiliently(opener, req, timeout=15)
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
        return []

def fetch_live_users(opener):
    if not opener:
        return []
    try:
        fields = json.dumps(["name", "email", "full_name", "first_name", "last_name", "enabled"])
        url = f"{ERPNEXT_SERVER_URL}/api/resource/User?fields={urllib.parse.quote(fields)}&limit_page_length=3000"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        res = call_erpnext_resiliently(opener, req, timeout=15)
        data = json.loads(res.read().decode("utf-8")).get("data", [])
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live users: {e}")
        return []


def _fetch_live_doctype_names(opener, doctype, limit=500):
    """Fetches authoritative live record names from a connected ERPNext Staging DocType (returns [] when empty)."""
    if not opener or not doctype:
        return []
    try:
        fields = urllib.parse.quote(json.dumps(["name"]))
        url = f"{ERPNEXT_SERVER_URL}/api/resource/{urllib.parse.quote(doctype, safe='')}?fields={fields}&order_by=name%20asc&limit_page_length={int(limit)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        res = call_erpnext_resiliently(opener, req, timeout=10)
        rows = json.loads(res.read().decode("utf-8")).get("data", [])
        if isinstance(rows, list):
            return [safe_str(r.get("name")) for r in rows if isinstance(r, dict) and safe_str(r.get("name"))]
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live {doctype}: {e}")
    return []


def fetch_live_item_groups(opener):
    return _fetch_live_doctype_names(opener, "Item Group", limit=500)


def fetch_live_fiscal_years(opener):
    return _fetch_live_doctype_names(opener, "Fiscal Year", limit=100)


def fetch_live_distributions(opener):
    return _fetch_live_doctype_names(opener, "Monthly Distribution", limit=200)


def fetch_live_departments(opener):
    return _fetch_live_doctype_names(opener, "Department", limit=500)


def fetch_live_designations(opener):
    return _fetch_live_doctype_names(opener, "Designation", limit=500)


def fetch_live_hcp_accounts(opener):
    """Fetches live covered HCP doctor accounts directly from ERPNext Staging (returns [] when DocType is empty)."""
    if not opener:
        return []
    for fields_list in [
        ["name", "hcp", "hcp_name", "doctor_name", "specialty", "specialization", "workplace_name", "institution_name", "workplace_id", "territory", "territory_code", "sales_person", "medrep_name", "account_or_program", "program"],
        ["name", "hcp", "hcp_name", "workplace_id", "territory", "sales_person"],
        ["name", "territory"]
    ]:
        try:
            fields = urllib.parse.quote(json.dumps(fields_list))
            url = f"{ERPNEXT_SERVER_URL}/api/resource/HCP%20Account?fields={fields}&limit_page_length=2500"
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            res = call_erpnext_resiliently(opener, req, timeout=12)
            rows = json.loads(res.read().decode("utf-8")).get("data", [])
            if isinstance(rows, list):
                normalized = []
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    normalized.append({
                        "accName": safe_str(r.get("name")),
                        "hcpId": safe_str(r.get("hcp") or r.get("name")),
                        "doctor": safe_str(r.get("hcp_name") or r.get("doctor_name") or r.get("hcp") or r.get("name")),
                        "spec": safe_str(r.get("specialty") or r.get("specialization")),
                        "hospital": safe_str(r.get("workplace_name") or r.get("institution_name") or r.get("workplace_id")),
                        "liveTerritory": safe_str(r.get("territory") or r.get("territory_code")),
                        "rep": safe_str(r.get("sales_person") or r.get("medrep_name")),
                        "program": safe_str(r.get("account_or_program") or r.get("program"))
                    })
                return normalized
        except Exception as e:
            print(f"[Streamlit Proxy] fetch_live_hcp_accounts fallback with {fields_list}: {e}")
            continue
    return []


def fetch_live_institutions(opener):
    if not opener:
        return []
    try:
        fields = json.dumps(["*"])
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Institution?fields={urllib.parse.quote(fields)}&order_by=name%20desc&limit_page_length=2500"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            res = call_erpnext_resiliently(opener, req, timeout=15)
            data = json.loads(res.read().decode("utf-8")).get("data", [])
        except Exception:
            core_fields = json.dumps(["name", "institution_name", "status", "workflow_state", "approval_status", "region_name", "province_name", "city_municipality", "barangay_name", "street_address", "owner", "creation", "modified", "docstatus"])
            fallback_url = f"{ERPNEXT_SERVER_URL}/api/resource/Institution?fields={urllib.parse.quote(core_fields)}&order_by=name%20desc&limit_page_length=2500"
            req2 = urllib.request.Request(fallback_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            try:
                res2 = call_erpnext_resiliently(opener, req2, timeout=15)
                data = json.loads(res2.read().decode("utf-8")).get("data", [])
            except Exception:
                min_fields = json.dumps(["name", "institution_name", "status", "region_name", "province_name", "city_municipality", "barangay_name", "street_address", "owner", "creation", "modified", "docstatus"])
                fallback_url2 = f"{ERPNEXT_SERVER_URL}/api/resource/Institution?fields={urllib.parse.quote(min_fields)}&order_by=name%20desc&limit_page_length=2500"
                req3 = urllib.request.Request(fallback_url2, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
                res3 = call_erpnext_resiliently(opener, req3, timeout=15)
                data = json.loads(res3.read().decode("utf-8")).get("data", [])

        # Hydrate audit trail and PIMS_META from Frappe Comment doctype
        # IMPORTANT: Live ERPNext Institution fields (status, workflow_state, docstatus) are ALWAYS authoritative over older comments!
        try:
            c_fields = json.dumps(["name", "reference_name", "content", "comment_by", "owner", "creation"])
            c_filters = json.dumps([["reference_doctype", "=", "Institution"]])
            c_url = f"{ERPNEXT_SERVER_URL}/api/resource/Comment?fields={urllib.parse.quote(c_fields)}&filters={urllib.parse.quote(c_filters)}&order_by=creation%20desc&limit_page_length=2500"
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
                # Snapshot authoritative live ERPNext status fields before hydrating comment metadata
                live_status = safe_str(inst.get("status"))
                live_wf = safe_str(inst.get("workflow_state"))
                live_approval = safe_str(inst.get("approval_status"))
                live_docstatus = int(inst.get("docstatus", 0) or 0)
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
                                if mv is not None and mv != "" and mk not in ("action", "user", "role", "timestamp", "details", "status", "workflow_state", "approval_status", "docstatus"):
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
                # Keep live ERPNext status strictly authoritative
                eff_live_state = live_wf or live_status or live_approval or ("Approved" if live_docstatus == 1 else ("Rejected" if live_docstatus == 2 else "Draft"))
                inst["status"] = live_status or eff_live_state
                inst["workflow_state"] = eff_live_state
                inst["docstatus"] = live_docstatus
                inst["audit_trail"] = audit_trail
        except Exception as ce:
            print(f"[Streamlit Proxy] Comment hydration notice: {ce}")

        # MedRep Proposal Detection & Live ERPNext Status Normalization
        if isinstance(data, list):
            for inst in data:
                if not isinstance(inst, dict):
                    continue
                iname = safe_str(inst.get("name"))
                owner = safe_str(inst.get("owner")).lower()
                remarks = (safe_str(inst.get("remarks")) + " " + safe_str(inst.get("custom_remarks")) + " " + safe_str(inst.get("certification_note"))).lower()
                doc_st = int(inst.get("docstatus", 0) or 0)
                wf_st = safe_str(inst.get("workflow_state") or inst.get("status") or inst.get("approval_status"))
                if not wf_st:
                    wf_st = "Approved" if doc_st == 1 else ("Rejected" if doc_st == 2 else "Draft")
                inst["workflow_state"] = wf_st
                if not safe_str(inst.get("status")):
                    inst["status"] = wf_st

                wf_low = wf_st.lower()
                # If already explicitly Approved, Rejected, Remapped, or Pending DSM Approval in ERPNext, NEVER demote back to Draft/Proposal!
                if wf_low in ("approved", "rejected", "remapped", "pending dsm approval") or doc_st in (1, 2):
                    if wf_low == "approved" or doc_st == 1:
                        inst["workflow_state"] = "Approved"
                        inst["status"] = "Approved"
                        inst["is_proposal"] = 0
                        inst["is_medrep_submission"] = 0
                    continue

                is_prop = (
                    inst.get("is_proposal") == 1 or
                    inst.get("is_medrep_submission") == 1 or
                    wf_low in ("pending approval", "pending review", "proposal") or
                    iname.startswith("INST-PROP-") or
                    "proposed" in remarks or
                    "certified by medrep" in remarks or
                    bool(inst.get("linked_doctor_name")) or
                    bool(inst.get("certification_note")) or
                    inst.get("is_certified") == 1 or
                    (owner and "profinsights.biz" not in owner and "administrator" not in owner and "guest" not in owner) or
                    (iname.startswith("INST-") and iname > "INST-09341")
                )
                if is_prop:
                    inst["is_proposal"] = 1
                    inst["is_medrep_submission"] = 1
                    if not wf_st or wf_low == "draft":
                        inst["workflow_state"] = "Pending Approval"

        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live institutions: {e}")
        return []


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


def _sync_institution_status_to_erpnext(opener, name, target_state, headers_json, wf_action=None, extra_fields=None):
    """
    Synchronizes Institution approval status directly to ERPNext Institution DocType
    across Frappe Workflow, `status`, and `workflow_state` fields so both ERPNext
    and the HCP Nexus App always reflect the exact live approval status.
    """
    if not opener or not name:
        return False, "Missing ERPNext session or Institution ID."
    synced = False
    last_err = ""
    if wf_action:
        try:
            wf_body = json.dumps({"doc": {"doctype": "Institution", "name": name}, "action": wf_action}).encode("utf-8")
            wf_req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/method/frappe.model.workflow.apply_workflow",
                data=wf_body,
                headers=headers_json,
                method="POST"
            )
            wf_res = call_erpnext_resiliently(opener, wf_req, timeout=12)
            if wf_res.status == 200:
                synced = True
        except Exception as wfe:
            last_err = str(wfe)

    put_url = f"{ERPNEXT_SERVER_URL}/api/resource/Institution/{urllib.parse.quote(name, safe='')}"
    base_extra = dict(extra_fields or {})
    # Progressive field updates: always ensure `status` and/or `workflow_state` are persisted on Institution DocType
    candidate_payloads = [
        {**base_extra, "status": target_state, "workflow_state": target_state},
        {**base_extra, "status": target_state},
        {**base_extra, "workflow_state": target_state},
        {"status": target_state},
        {"workflow_state": target_state},
    ]
    for payload_dict in candidate_payloads:
        try:
            put_req = urllib.request.Request(
                put_url,
                data=json.dumps(payload_dict).encode("utf-8"),
                headers=headers_json,
                method="PUT"
            )
            put_res = call_erpnext_resiliently(opener, put_req, timeout=12)
            if put_res.status == 200:
                synced = True
                break
        except urllib.error.HTTPError as he:
            last_err = _extract_erp_http_error(he) or last_err
        except Exception as ex:
            last_err = str(ex) or last_err

    if not synced:
        for field_key in ("status", "workflow_state"):
            try:
                sv_body = json.dumps({
                    "doctype": "Institution",
                    "name": name,
                    "fieldname": field_key,
                    "value": target_state
                }).encode("utf-8")
                sv_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.set_value",
                    data=sv_body,
                    headers=headers_json,
                    method="POST"
                )
                sv_res = call_erpnext_resiliently(opener, sv_req, timeout=12)
                if sv_res.status == 200:
                    synced = True
                    break
            except urllib.error.HTTPError as he:
                last_err = _extract_erp_http_error(he) or last_err
            except Exception as ex:
                last_err = str(ex) or last_err

    return synced, ("" if synced else (last_err or f"ERPNext rejected status update to '{target_state}'."))


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
            target_docstatus = 0
            wf_action = "Route to DSM" if needs_dsm else "Approve"

            if not name:
                return "error", "Institution ID is required."

            synced_ok, sync_err = _sync_institution_status_to_erpnext(
                opener,
                name,
                target_state,
                headers_json,
                wf_action=wf_action,
                extra_fields={"rejection_reason": ""}
            )
            if not synced_ok:
                return "error", f'Could not update Institution "{inst_title}" ({name}) to {target_state} on {get_server_display_name()}: {sync_err}'

            human_msg = (
                f"Validated by {actor_user} ({actor_role}) in Web Portal and routed to DSM for regional approval."
                if needs_dsm else
                f"Approved by {actor_user} ({actor_role}) in Web Portal. Facility status synced as Approved in ERPNext & HCP Nexus App."
            )
            _post_institution_meta_comment(opener, name, human_msg, {
                "status": target_state,
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

            return "success", f'Institution "{inst_title}" ({name}) {("routed to Pending DSM Approval" if needs_dsm else "approved and synced as Approved to ERPNext & HCP Nexus App")}!'

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

            # Standard ERPNext fields for live creation (with Pending Approval status fallback)
            erp_inst_doc_base = {
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
            created_in_erp = False
            create_err = ""
            for doc_candidate in (
                {**erp_inst_doc_base, "status": "Pending Approval", "workflow_state": "Pending Approval"},
                {**erp_inst_doc_base, "status": "Pending Approval"},
                erp_inst_doc_base,
            ):
                try:
                    c_body = json.dumps(doc_candidate).encode("utf-8")
                    c_req = urllib.request.Request(f"{ERPNEXT_SERVER_URL}/api/resource/Institution", data=c_body, headers=headers_json, method="POST")
                    c_res = call_erpnext_resiliently(opener, c_req, timeout=10)
                    if c_res.status in [200, 201]:
                        c_data = json.loads(c_res.read().decode("utf-8")).get("data", {})
                        if c_data.get("name"):
                            new_rec["erp_name"] = c_data["name"]
                        created_in_erp = True
                        break
                except urllib.error.HTTPError as he:
                    create_err = _extract_erp_http_error(he) or create_err
                except Exception as ex:
                    create_err = str(ex) or create_err
            if not created_in_erp:
                return "error", f'Could not create Institution proposal "{inst_title}" on {get_server_display_name()}: {create_err or "ERPNext rejected creation"}'

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
                wf_action = "Route to DSM" if needs_dsm else "Approve"
                synced_ok, sync_err = _sync_institution_status_to_erpnext(
                    opener,
                    name,
                    target_state,
                    headers_json,
                    wf_action=wf_action,
                    extra_fields={"rejection_reason": ""}
                )
                if not synced_ok:
                    return "error", f'Normalized fields saved, but ERPNext rejected status update to "{target_state}" for "{clean_wp}" ({name}): {sync_err}'

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
            synced_ok, sync_err = _sync_institution_status_to_erpnext(
                opener,
                name,
                "Rejected",
                headers_json,
                wf_action="Reject",
                extra_fields={"rejection_reason": reason}
            )
            if not synced_ok:
                return "error", f'Could not reject Institution "{inst_title}" ({name}) on {get_server_display_name()}: {sync_err}'

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

            synced_ok, sync_err = _sync_institution_status_to_erpnext(
                opener,
                old_id,
                "Remapped",
                headers_json,
                wf_action="Remap",
                extra_fields={"rejection_reason": full_note}
            )
            if not synced_ok:
                return "error", f'Could not remap Institution "{old_name}" ({old_id}) on {get_server_display_name()}: {sync_err}'

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

_TERRITORY_ROOT_CACHE = None

def _get_territory_root_node(opener, headers_json):
    """Detects the top-level root folder in ERPNext Territory tree (typically 'All Territories')."""
    global _TERRITORY_ROOT_CACHE
    if _TERRITORY_ROOT_CACHE:
        return _TERRITORY_ROOT_CACHE
    if not opener:
        return None
    try:
        fields = urllib.parse.quote(json.dumps(["name", "parent_territory", "is_group"]))
        flt = urllib.parse.quote(json.dumps([["Territory", "is_group", "=", 1]]))
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory?fields={fields}&filters={flt}&limit_page_length=200"
        res = call_erpnext_resiliently(opener, urllib.request.Request(url, headers=headers_json), timeout=6)
        rows = json.loads(res.read().decode("utf-8")).get("data", [])
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and not safe_str(r.get("parent_territory")):
                    _TERRITORY_ROOT_CACHE = safe_str(r.get("name"))
                    if _TERRITORY_ROOT_CACHE:
                        return _TERRITORY_ROOT_CACHE
            for r in rows:
                if isinstance(r, dict) and safe_str(r.get("name")).lower() == "all territories":
                    _TERRITORY_ROOT_CACHE = safe_str(r.get("name"))
                    return _TERRITORY_ROOT_CACHE
    except Exception:
        pass
    return None

def _ensure_territory_root_exists(opener, headers_json):
    """Ensures a root Territory node exists in ERPNext (bootstrapping 'All Territories' if DocType is empty)."""
    global _TERRITORY_ROOT_CACHE
    root_name = _get_territory_root_node(opener, headers_json)
    if root_name:
        return True, root_name, ""
    if not opener:
        return False, "", "No active ERPNext session."
    last_err = ""
    try:
        c_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
            data=json.dumps({
                "territory_name": "All Territories",
                "parent_territory": "",
                "is_group": 1
            }).encode("utf-8"),
            headers=headers_json,
            method="POST"
        )
        res = call_erpnext_resiliently(opener, c_req, timeout=10)
        if res.status in [200, 201]:
            _TERRITORY_ROOT_CACHE = "All Territories"
            return True, "All Territories", ""
    except urllib.error.HTTPError as he:
        err_msg = _extract_erp_http_error(he)
        if "DuplicateEntryError" in err_msg:
            _TERRITORY_ROOT_CACHE = "All Territories"
            return True, "All Territories", ""
        last_err = err_msg
    except Exception as ex:
        last_err = str(ex)
    try:
        form_data = urllib.parse.urlencode({
            "doctype": "Territory",
            "parent": "",
            "territory_name": "All Territories",
            "is_group": "1",
            "is_root": "true"
        }).encode("utf-8")
        tv_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/method/frappe.desk.treeview.add_node",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        tv_res = call_erpnext_resiliently(opener, tv_req, timeout=10)
        if tv_res.status in [200, 201]:
            _TERRITORY_ROOT_CACHE = "All Territories"
            return True, "All Territories", ""
    except urllib.error.HTTPError as he:
        last_err = _extract_erp_http_error(he) or last_err
    except Exception as ex:
        last_err = str(ex) or last_err
    return False, "All Territories", last_err

def _ensure_parent_territory_is_group(opener, parent_name, headers_json):
    """Ensure a parent territory exists and has is_group=1 on ERPNext before attaching child territories under it."""
    parent_clean = safe_str(parent_name)
    if not opener:
        return False, parent_clean or "All Territories", "No active ERPNext session."
    root_ok, root_terr, root_err = _ensure_territory_root_exists(opener, headers_json)
    effective_root = root_terr or "All Territories"
    if not parent_clean or parent_clean.lower() in ("all territories", effective_root.lower()):
        return root_ok, effective_root, root_err
    last_err = ""
    try:
        chk_url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(parent_clean, safe='')}"
        chk_req = urllib.request.Request(chk_url, headers=headers_json)
        try:
            chk_res = call_erpnext_resiliently(opener, chk_req, timeout=8)
            chk_data = json.loads(chk_res.read().decode("utf-8")).get("data", {})
            actual_name = safe_str(chk_data.get("name")) or parent_clean
            if not chk_data.get("is_group"):
                promoted = False
                try:
                    promote_req = urllib.request.Request(
                        chk_url,
                        data=json.dumps({"is_group": 1}).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    )
                    p_res = call_erpnext_resiliently(opener, promote_req, timeout=8)
                    promoted = (p_res.status == 200)
                except Exception:
                    pass
                if not promoted:
                    try:
                        sv_data = urllib.parse.urlencode({
                            "doctype": "Territory",
                            "name": actual_name,
                            "fieldname": "is_group",
                            "value": "1"
                        }).encode("utf-8")
                        call_erpnext_resiliently(opener, urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.set_value",
                            data=sv_data,
                            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                            method="POST"
                        ), timeout=8)
                    except Exception:
                        pass
            return True, actual_name, ""
        except urllib.error.HTTPError as he:
            if he.code == 404:
                # Parent does not exist yet! Create it under effective_root with is_group=1
                post_body = {
                    "territory_name": parent_clean,
                    "parent_territory": effective_root,
                    "is_group": 1
                }
                try:
                    c_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                        data=json.dumps(post_body).encode("utf-8"),
                        headers=headers_json,
                        method="POST"
                    )
                    c_res = call_erpnext_resiliently(opener, c_req, timeout=8)
                    if c_res.status in [200, 201]:
                        return True, parent_clean, ""
                except urllib.error.HTTPError as che:
                    last_err = _extract_erp_http_error(che)
                    if "DuplicateEntryError" in last_err:
                        return True, parent_clean, ""
                except Exception as cex:
                    last_err = str(cex)
                # Fallback: Frappe TreeView add_node for parent group creation
                try:
                    tv_data = urllib.parse.urlencode({
                        "doctype": "Territory",
                        "parent": effective_root,
                        "territory_name": parent_clean,
                        "is_group": "1",
                        "is_root": "false"
                    }).encode("utf-8")
                    tv_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/method/frappe.desk.treeview.add_node",
                        data=tv_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                        method="POST"
                    )
                    tv_res = call_erpnext_resiliently(opener, tv_req, timeout=8)
                    if tv_res.status in [200, 201]:
                        return True, parent_clean, ""
                except urllib.error.HTTPError as tvhe:
                    last_err = _extract_erp_http_error(tvhe) or last_err
                except Exception as tvex:
                    last_err = str(tvex) or last_err
                return False, parent_clean, last_err
            else:
                last_err = _extract_erp_http_error(he)
                return False, parent_clean, last_err
    except Exception as ex:
        return False, parent_clean, str(ex)
    return True, parent_clean, ""


_DISTRICT_CUSTOM_FIELDS_ENSURED = False
_SALES_PERSON_ROOT_CACHE = None

def _extract_erp_http_error(http_err):
    """Extracts a human-readable Frappe/ERPNext error message from urllib HTTPError."""
    try:
        body_txt = http_err.read().decode("utf-8", errors="ignore")
        body_json = json.loads(body_txt) if body_txt else {}
        msg_val = body_json.get("exception") or body_json.get("message")
        if not msg_val and body_json.get("_server_messages"):
            msgs = json.loads(body_json["_server_messages"])
            if msgs:
                m_obj = json.loads(msgs[0]) if isinstance(msgs[0], str) else msgs[0]
                msg_val = m_obj.get("message") if isinstance(m_obj, dict) else str(m_obj)
        return str(msg_val or body_txt or f"HTTP Error {http_err.code}")
    except Exception:
        return f"HTTP Error {getattr(http_err, 'code', 'Unknown')}"

def _ensure_district_custom_fields(opener, headers_json):
    """Ensures custom_district field exists on Sales Person and Territory DocTypes when permitted."""
    global _DISTRICT_CUSTOM_FIELDS_ENSURED
    if _DISTRICT_CUSTOM_FIELDS_ENSURED or not opener:
        return
    _DISTRICT_CUSTOM_FIELDS_ENSURED = True
    for dt, insert_after in [("Sales Person", "department"), ("Territory", "territory_manager")]:
        cf_name = f"{dt}-custom_district"
        chk_url = f"{ERPNEXT_SERVER_URL}/api/resource/Custom%20Field/{urllib.parse.quote(cf_name, safe='')}"
        try:
            call_erpnext_resiliently(opener, urllib.request.Request(chk_url, headers=headers_json), timeout=5)
        except urllib.error.HTTPError as he:
            if he.code == 404:
                try:
                    cf_body = {
                        "dt": dt,
                        "fieldname": "custom_district",
                        "label": "District",
                        "fieldtype": "Data",
                        "insert_after": insert_after
                    }
                    cf_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Custom%20Field",
                        data=json.dumps(cf_body).encode("utf-8"),
                        headers=headers_json,
                        method="POST"
                    )
                    call_erpnext_resiliently(opener, cf_req, timeout=8)
                except Exception:
                    pass
        except Exception:
            pass

def _get_sales_person_root_node(opener, headers_json):
    """Detects the top-level root folder in ERPNext Sales Person tree (returns None if DocType is empty)."""
    global _SALES_PERSON_ROOT_CACHE
    if _SALES_PERSON_ROOT_CACHE:
        return _SALES_PERSON_ROOT_CACHE
    if not opener:
        return None
    try:
        fields = urllib.parse.quote(json.dumps(["name", "parent_sales_person", "is_group"]))
        flt = urllib.parse.quote(json.dumps([["Sales Person", "is_group", "=", 1]]))
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person?fields={fields}&filters={flt}&limit_page_length=200"
        res = call_erpnext_resiliently(opener, urllib.request.Request(url, headers=headers_json), timeout=6)
        rows = json.loads(res.read().decode("utf-8")).get("data", [])
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and not safe_str(r.get("parent_sales_person")):
                    _SALES_PERSON_ROOT_CACHE = safe_str(r.get("name"))
                    if _SALES_PERSON_ROOT_CACHE:
                        return _SALES_PERSON_ROOT_CACHE
            for r in rows:
                if isinstance(r, dict) and safe_str(r.get("name")).lower() == "sales team":
                    _SALES_PERSON_ROOT_CACHE = safe_str(r.get("name"))
                    return _SALES_PERSON_ROOT_CACHE
    except Exception:
        pass
    return None

def _ensure_sales_person_root_exists(opener, headers_json):
    """Ensures a root Sales Person group exists on ERPNext, bootstrapping 'Sales Team' if DocType is empty."""
    global _SALES_PERSON_ROOT_CACHE
    existing_root = _get_sales_person_root_node(opener, headers_json)
    if existing_root:
        return True, existing_root, ""
    if not opener:
        return False, "", "No active ERPNext session."
    ok, created_name, err_msg = _create_sp_via_rest_or_treeview(
        opener,
        "Sales Team",
        "",
        1,
        {"enabled": 1},
        headers_json
    )
    if ok:
        _SALES_PERSON_ROOT_CACHE = created_name or "Sales Team"
        return True, _SALES_PERSON_ROOT_CACHE, ""
    return False, "", err_msg

def _find_existing_sales_person(opener, sp_name, headers_json):
    """Finds an existing Sales Person record by exact or case-insensitive name."""
    clean = safe_str(sp_name)
    if not clean or not opener:
        return None
    chk_url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(clean, safe='')}"
    try:
        r = call_erpnext_resiliently(opener, urllib.request.Request(chk_url, headers=headers_json), timeout=6)
        data = json.loads(r.read().decode("utf-8")).get("data")
        if isinstance(data, dict) and data.get("name"):
            return data
    except urllib.error.HTTPError:
        pass
    except Exception:
        pass
    try:
        fields = urllib.parse.quote(json.dumps(["name", "sales_person_name", "parent_sales_person", "is_group"]))
        flt = urllib.parse.quote(json.dumps([["Sales Person", "name", "like", clean]]))
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person?fields={fields}&filters={flt}&limit_page_length=10"
        r = call_erpnext_resiliently(opener, urllib.request.Request(url, headers=headers_json), timeout=6)
        rows = json.loads(r.read().decode("utf-8")).get("data", [])
        if isinstance(rows, list):
            for row in rows:
                rn = safe_str(row.get("name"))
                sn = safe_str(row.get("sales_person_name"))
                if rn.lower() == clean.lower() or sn.lower() == clean.lower():
                    return row
    except Exception:
        pass
    return None

def _create_sp_via_rest_or_treeview(opener, sp_name, parent_sp, is_group, base_body, headers_json):
    """Creates or updates a Sales Person record via REST API with Frappe TreeView add_node fallback."""
    clean_sp = safe_str(sp_name)
    last_err = ""

    def _try_rest_post(payload_dict):
        data = json.dumps(payload_dict).encode("utf-8")
        p_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person",
            data=data,
            headers=headers_json,
            method="POST"
        )
        try:
            r = call_erpnext_resiliently(opener, p_req, timeout=12)
            return r.status in [200, 201], "", ""
        except urllib.error.HTTPError as he:
            err_msg = _extract_erp_http_error(he)
            if "DuplicateEntryError" in err_msg:
                up_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(clean_sp, safe='')}",
                    data=data,
                    headers=headers_json,
                    method="PUT"
                )
                try:
                    ur = call_erpnext_resiliently(opener, up_req, timeout=12)
                    if ur.status in [200, 201]:
                        return True, clean_sp, ""
                except urllib.error.HTTPError as uhe:
                    return False, "", _extract_erp_http_error(uhe)
                except Exception as uex:
                    return False, "", str(uex)
            return False, "", err_msg
        except Exception as ex:
            return False, "", str(ex)

    attempt_body = dict(base_body)
    attempt_body["sales_person_name"] = clean_sp
    clean_parent = safe_str(parent_sp)
    if clean_parent:
        attempt_body["parent_sales_person"] = clean_parent
    else:
        attempt_body.pop("parent_sales_person", None)
    attempt_body["is_group"] = int(is_group or 0)

    ok, created_name, err = _try_rest_post(attempt_body)
    if ok:
        return True, created_name or clean_sp, ""
    last_err = err

    # Progressive fallback: strip optional fields ONLY — strictly preserve parent_sales_person!
    for opt_field in ("custom_district", "targets", "department", "employee", "commission_rate"):
        if opt_field in attempt_body:
            del attempt_body[opt_field]
            ok, created_name, err = _try_rest_post(attempt_body)
            if ok:
                return True, created_name or clean_sp, ""
            last_err = err

    # Fallback 1: Frappe native TreeView add_node endpoint (/app/sales-person/view/tree)
    try:
        form_data = urllib.parse.urlencode({
            "doctype": "Sales Person",
            "parent": clean_parent,
            "sales_person_name": clean_sp,
            "is_group": str(int(is_group or 0)),
            "is_root": "true" if not clean_parent else "false"
        }).encode("utf-8")
        tv_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/method/frappe.desk.treeview.add_node",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        tv_res = call_erpnext_resiliently(opener, tv_req, timeout=12)
        if tv_res.status in [200, 201]:
            if safe_str(base_body.get("custom_district")) or safe_str(base_body.get("employee")):
                extra_put = {}
                if safe_str(base_body.get("custom_district")):
                    extra_put["custom_district"] = safe_str(base_body.get("custom_district"))
                if safe_str(base_body.get("employee")):
                    extra_put["employee"] = safe_str(base_body.get("employee"))
                try:
                    call_erpnext_resiliently(opener, urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(clean_sp, safe='')}",
                        data=json.dumps(extra_put).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    ), timeout=8)
                except Exception:
                    pass
            return True, clean_sp, ""
    except urllib.error.HTTPError as tv_he:
        last_err = _extract_erp_http_error(tv_he) or last_err
    except Exception as tv_ex:
        last_err = str(tv_ex) or last_err

    # Fallback 2: Frappe Desk frappe.client.insert RPC
    try:
        doc_payload = {
            "doctype": "Sales Person",
            "sales_person_name": clean_sp,
            "is_group": int(is_group or 0),
            "enabled": int(base_body.get("enabled", 1) if base_body.get("enabled") is not None else 1)
        }
        if clean_parent:
            doc_payload["parent_sales_person"] = clean_parent
        ins_data = urllib.parse.urlencode({"doc": json.dumps(doc_payload)}).encode("utf-8")
        ins_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.insert",
            data=ins_data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        ins_res = call_erpnext_resiliently(opener, ins_req, timeout=12)
        if ins_res.status in [200, 201]:
            return True, clean_sp, ""
    except urllib.error.HTTPError as ins_he:
        last_err = _extract_erp_http_error(ins_he) or last_err
    except Exception as ins_ex:
        last_err = str(ins_ex) or last_err

    # Check whether another process created it concurrently
    existing_after = _find_existing_sales_person(opener, clean_sp, headers_json)
    if existing_after:
        return True, existing_after.get("name") or clean_sp, ""

    return False, "", last_err or f"Failed creating Sales Person '{clean_sp}' on ERPNext."

def _ensure_parent_sales_person_is_group(opener, parent_name, headers_json, parent_of_parent=""):
    """Ensure a parent sales person exists and has is_group=1 on ERPNext before attaching child sales persons under it."""
    if not opener:
        return False, "", "No active ERPNext session."
    root_ok, root_sp, root_err = _ensure_sales_person_root_exists(opener, headers_json)
    parent_clean = safe_str(parent_name)
    if not parent_clean or (root_sp and parent_clean.lower() in ("sales team", root_sp.lower())) or (not root_sp and parent_clean.lower() == "sales team"):
        if root_ok and root_sp:
            return True, root_sp, ""
        return False, "", root_err or "Could not verify or create root Sales Person ('Sales Team') on ERPNext."

    existing = _find_existing_sales_person(opener, parent_clean, headers_json)
    if existing:
        actual_name = existing.get("name") or parent_clean
        if not existing.get("is_group"):
            put_url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(actual_name, safe='')}"
            promoted = False
            try:
                p_res = call_erpnext_resiliently(opener, urllib.request.Request(
                    put_url,
                    data=json.dumps({"is_group": 1}).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                ), timeout=8)
                if p_res.status == 200:
                    promoted = True
            except Exception:
                pass
            if not promoted:
                try:
                    sv_data = urllib.parse.urlencode({
                        "doctype": "Sales Person",
                        "name": actual_name,
                        "fieldname": "is_group",
                        "value": "1"
                    }).encode("utf-8")
                    call_erpnext_resiliently(opener, urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.set_value",
                        data=sv_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                        method="POST"
                    ), timeout=8)
                except Exception:
                    pass
        return True, actual_name, ""

    target_upper = root_sp
    clean_upper = safe_str(parent_of_parent)
    if clean_upper and clean_upper.lower() not in ("sales team", root_sp.lower(), parent_clean.lower()):
        up_ok, resolved_upper, _ = _ensure_parent_sales_person_is_group(opener, clean_upper, headers_json)
        if up_ok and resolved_upper:
            target_upper = resolved_upper

    ok, created_parent, err_msg = _create_sp_via_rest_or_treeview(
        opener,
        parent_clean,
        target_upper,
        1,
        {"enabled": 1},
        headers_json
    )
    if ok:
        record_shared_sales_person_meta(created_parent, parent_sp=target_upper, is_group=1, pending_erp_sync=False)
        return True, created_parent, ""
    return False, "", err_msg

def _ensure_sales_person_exists_in_erpnext(
    opener,
    sp_name,
    headers_json,
    parent_sp="",
    is_group=0,
    employee="",
    district="",
    department="",
    enabled=1,
    commission_rate=None,
    targets=None,
    program="",
    grand_parent_sp=""
):
    """Creates or updates a Sales Person (plus parent group folder if missing) and records District/Program metadata."""
    clean_sp = safe_str(sp_name)
    if not clean_sp:
        return False, "", "Sales Person Name cannot be blank."
    if not opener:
        return False, "", "No active ERPNext connection."

    _ensure_district_custom_fields(opener, headers_json)
    p_ok, resolved_parent, p_err = _ensure_parent_sales_person_is_group(
        opener,
        parent_sp,
        headers_json,
        parent_of_parent=grand_parent_sp
    )
    if not p_ok:
        return False, "", f'Could not create/verify Parent Sales Person "{parent_sp}": {p_err}'

    body = {
        "sales_person_name": clean_sp,
        "parent_sales_person": resolved_parent,
        "is_group": int(is_group or 0),
        "enabled": int(enabled if enabled is not None else 1)
    }
    if safe_str(employee):
        body["employee"] = safe_str(employee)
    if safe_str(department):
        body["department"] = safe_str(department)
    if safe_str(district):
        body["custom_district"] = safe_str(district)
    if commission_rate is not None and commission_rate != "":
        try:
            body["commission_rate"] = float(commission_rate)
        except Exception:
            pass
    if targets and isinstance(targets, list) and len(targets) > 0:
        cleaned_targets = []
        for t in targets:
            if isinstance(t, dict):
                item_grp = safe_str(t.get("item_group")) or "All Item Groups"
                dist_id = safe_str(t.get("distribution_id")) or "Evenly Distributed"
                try:
                    qty = float(t.get("target_qty") or 0)
                except Exception:
                    qty = 0.0
                try:
                    amt = float(t.get("target_amount") or 0)
                except Exception:
                    amt = 0.0
                if item_grp or qty > 0 or amt > 0:
                    cleaned_targets.append({
                        "item_group": item_grp,
                        "fiscal_year": safe_str(t.get("fiscal_year")) or "2026",
                        "target_qty": qty,
                        "target_amount": amt,
                        "distribution_id": dist_id
                    })
        if cleaned_targets:
            body["targets"] = cleaned_targets

    ok, created_name, err_msg = _create_sp_via_rest_or_treeview(
        opener,
        clean_sp,
        resolved_parent,
        int(is_group or 0),
        body,
        headers_json
    )
    if not ok:
        return False, "", err_msg

    record_shared_sales_person_meta(
        created_name,
        parent_sp=resolved_parent,
        is_group=int(is_group or 0),
        district=safe_str(district) if district is not None else None,
        program=safe_str(program) if program else None,
        employee=safe_str(employee) if employee else None,
        pending_erp_sync=False
    )
    return True, created_name, ""


def _sync_sales_person_code_on_territory_rename(opener, old_terr, new_terr, headers_json, assigned_mgr="", prev_terr=""):
    """
    Synchronizes the parenthesized territory code suffix in ERPNext's Sales Person Tree
    (e.g. 'ARCENE PIANG (AD0116)' -> 'ARCENE PIANG (AD0900)') whenever a territory is renamed.
    Preserves the MedRep base name and updates linked Territory Manager references cleanly.
    """
    clean_old = safe_str(old_terr)
    clean_new = safe_str(new_terr)
    if not opener or not clean_old or not clean_new or clean_old.lower() == clean_new.lower():
        return []

    renamed_results = []
    try:
        live_sps = fetch_live_sales_persons(opener)
        if not isinstance(live_sps, list):
            live_sps = st.session_state.get("live_sales_persons") or []

        # Probe live Territory on ERPNext to retrieve exact Territory.territory_manager and is_group
        live_terr_mgr = safe_str(assigned_mgr)
        erpn_mgr = ""
        terr_is_group = None
        for probe_terr in (clean_new, clean_old):
            try:
                t_url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(probe_terr, safe='')}"
                t_res = call_erpnext_resiliently(opener, urllib.request.Request(t_url, headers=headers_json), timeout=6)
                t_data = json.loads(t_res.read().decode("utf-8")).get("data", {})
                if "is_group" in t_data:
                    terr_is_group = int(t_data.get("is_group") or 0)
                if t_data.get("territory_manager"):
                    erpn_mgr = safe_str(t_data.get("territory_manager"))
                break
            except Exception:
                pass

        if erpn_mgr:
            live_terr_mgr = erpn_mgr

        if terr_is_group is None and "live_territories" in st.session_state and isinstance(st.session_state.live_territories, list):
            for lt in st.session_state.live_territories:
                if isinstance(lt, dict) and safe_str(lt.get("name") or lt.get("territory_name")) in (clean_new, clean_old):
                    terr_is_group = int(lt.get("is_group") or 0)
                    if not live_terr_mgr and lt.get("territory_manager"):
                        live_terr_mgr = safe_str(lt.get("territory_manager"))
                    break
        terr_is_group = int(terr_is_group or 0)

        sp_by_lower = {}
        for sp in live_sps:
            if not isinstance(sp, dict):
                continue
            sp_key = safe_str(sp.get("name") or sp.get("sales_person_name"))
            if sp_key:
                sp_by_lower[sp_key.lower()] = sp

        targets = []
        seen_old = set()

        # 1. Exact match on parenthesized old_terr across Sales Person Tree
        for sp in live_sps:
            if not isinstance(sp, dict):
                continue
            sp_id = safe_str(sp.get("name") or sp.get("sales_person_name"))
            sp_label = safe_str(sp.get("sales_person_name") or sp_id)
            if not sp_id or sp_id.lower() in seen_old:
                continue
            candidate_new = _replace_parenthesized_territory_code(sp_id, clean_old, clean_new)
            if not candidate_new:
                candidate_new = _replace_parenthesized_territory_code(sp_label, clean_old, clean_new)
            if candidate_new:
                seen_old.add(sp_id.lower())
                targets.append((sp, sp_id, candidate_new))

        # 2. If territory was previously renamed / pre-mismatched, check non-group assigned manager against prior codes
        clean_prev = safe_str(prev_terr)
        clean_mgr_base = re.sub(r"\s*\([^)]*\)", "", live_terr_mgr).strip().lower() if live_terr_mgr else ""
        mgr_paren_match = re.search(r"\(\s*([^()]+?)\s*\)\s*$", live_terr_mgr) if live_terr_mgr else None
        mgr_paren_code = safe_str(mgr_paren_match.group(1)) if mgr_paren_match else ""
        prior_codes = []
        for p_cand in (clean_prev, mgr_paren_code):
            if p_cand and p_cand.lower() not in (clean_old.lower(), clean_new.lower()):
                if p_cand.lower() not in [x.lower() for x in prior_codes]:
                    prior_codes.append(p_cand)

        if not targets and not terr_is_group and prior_codes and (live_terr_mgr or clean_mgr_base):
            for sp in live_sps:
                if not isinstance(sp, dict) or int(sp.get("is_group") or 0):
                    continue
                sp_id = safe_str(sp.get("name") or sp.get("sales_person_name"))
                if not sp_id or sp_id.lower() in seen_old:
                    continue
                sp_base = re.sub(r"\s*\([^)]*\)", "", sp_id).strip().lower()
                if (live_terr_mgr and sp_id.lower() == live_terr_mgr.lower()) or (clean_mgr_base and sp_base == clean_mgr_base):
                    for p_code in prior_codes:
                        candidate_new = _replace_parenthesized_territory_code(sp_id, p_code, clean_new)
                        if candidate_new:
                            seen_old.add(sp_id.lower())
                            targets.append((sp, sp_id, candidate_new))
                            break

        # 3. Single-match leaf self-heal for pre-mismatched leaf records (e.g. AD0900 -> AD0901 with 'ARCENE PIANG (AD0116)')
        if not targets and not terr_is_group and (live_terr_mgr or clean_mgr_base):
            leaf_matches = []
            for sp in live_sps:
                if not isinstance(sp, dict) or int(sp.get("is_group") or 0):
                    continue
                sp_id = safe_str(sp.get("name") or sp.get("sales_person_name"))
                if not sp_id or sp_id.lower() in seen_old:
                    continue
                sp_base = re.sub(r"\s*\([^)]*\)", "", sp_id).strip().lower()
                exact_link = bool(live_terr_mgr and sp_id.lower() == live_terr_mgr.lower())
                if exact_link or (clean_mgr_base and sp_base == clean_mgr_base):
                    leaf_matches.append((exact_link, sp, sp_id))

            exact_leaves = [m for m in leaf_matches if m[0]]
            chosen = exact_leaves[0] if len(exact_leaves) == 1 else (leaf_matches[0] if len(leaf_matches) == 1 else None)
            if chosen:
                _, sp, sp_id = chosen
                m_code = re.search(r"\(\s*([^()]+?)\s*\)\s*$", sp_id)
                if m_code:
                    stale_code = safe_str(m_code.group(1))
                    if stale_code and stale_code.lower() != clean_new.lower():
                        candidate_new = _replace_parenthesized_territory_code(sp_id, stale_code, clean_new)
                        if candidate_new:
                            seen_old.add(sp_id.lower())
                            targets.append((sp, sp_id, candidate_new))
                elif not re.search(r"\([^)]+\)", sp_id):
                    # Leaf Sales Person had no parenthesized territory code yet -> append newly renamed territory code
                    candidate_new = f"{sp_id} ({clean_new})"
                    seen_old.add(sp_id.lower())
                    targets.append((sp, sp_id, candidate_new))

        for sp_obj, old_sp, new_sp in targets:
            is_terr_mgr = bool(
                live_terr_mgr and (
                    old_sp.lower() == live_terr_mgr.lower()
                    or re.sub(r"\s*\([^)]*\)", "", old_sp).strip().lower() == clean_mgr_base
                )
            )
            # Collision guard: avoid overwriting an existing distinct Sales Person record
            if new_sp.lower() in sp_by_lower and old_sp.lower() != new_sp.lower():
                existing_target = safe_str(sp_by_lower[new_sp.lower()].get("name") or new_sp)
                if is_terr_mgr:
                    try:
                        mgr_req = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(clean_new, safe='')}",
                            data=json.dumps({"territory_manager": existing_target}).encode("utf-8"),
                            headers=headers_json,
                            method="PUT"
                        )
                        call_erpnext_resiliently(opener, mgr_req, timeout=8)
                    except Exception:
                        pass
                continue

            sp_renamed = False
            try:
                sp_form = urllib.parse.urlencode({
                    "doctype": "Sales Person",
                    "old_name": old_sp,
                    "new_name": new_sp
                }).encode("utf-8")
                sp_req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.rename_doc",
                    data=sp_form,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                    method="POST"
                )
                sp_res = call_erpnext_resiliently(opener, sp_req, timeout=12)
                if sp_res and sp_res.status == 200:
                    sp_renamed = True
                    try:
                        sp_put = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(new_sp, safe='')}",
                            data=json.dumps({"sales_person_name": new_sp}).encode("utf-8"),
                            headers=headers_json,
                            method="PUT"
                        )
                        call_erpnext_resiliently(opener, sp_put, timeout=10)
                    except Exception:
                        pass
            except Exception as sp_err:
                print(f"[Sales Person Code Rename Warning] {old_sp} -> {new_sp}: {sp_err}")

            if sp_renamed:
                sp_by_lower.pop(old_sp.lower(), None)
                sp_by_lower[new_sp.lower()] = {**sp_obj, "name": new_sp, "sales_person_name": new_sp}
                record_shared_sales_person_rename(old_sp, new_sp)
                if is_terr_mgr:
                    record_shared_territory_edit(clean_new, manager=new_sp)
                    mgr_put_body = {"territory_manager": new_sp}
                    resolved_rename_uid = _resolve_medrep_user_id_from_sales_person(opener, new_sp, headers_json)
                    if resolved_rename_uid:
                        mgr_put_body["custom_user_id"] = resolved_rename_uid
                    try:
                        mgr_req = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(clean_new, safe='')}",
                            data=json.dumps(mgr_put_body).encode("utf-8"),
                            headers=headers_json,
                            method="PUT"
                        )
                        call_erpnext_resiliently(opener, mgr_req, timeout=8)
                    except Exception:
                        try:
                            mgr_req_fb = urllib.request.Request(
                                f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(clean_new, safe='')}",
                                data=json.dumps({"territory_manager": new_sp}).encode("utf-8"),
                                headers=headers_json,
                                method="PUT"
                            )
                            call_erpnext_resiliently(opener, mgr_req_fb, timeout=8)
                        except Exception:
                            pass

                # Reflect immediately in session state (including child parent_sales_person links)
                if "live_sales_persons" in st.session_state and isinstance(st.session_state.live_sales_persons, list):
                    for s in st.session_state.live_sales_persons:
                        if not isinstance(s, dict):
                            continue
                        if s.get("name") == old_sp or s.get("sales_person_name") == old_sp:
                            s["name"] = new_sp
                            s["sales_person_name"] = new_sp
                        if s.get("parent_sales_person") == old_sp:
                            s["parent_sales_person"] = new_sp

                if "live_territories" in st.session_state and isinstance(st.session_state.live_territories, list):
                    for t in st.session_state.live_territories:
                        if isinstance(t, dict) and safe_str(t.get("territory_manager")).lower() == old_sp.lower():
                            t["territory_manager"] = new_sp

                renamed_results.append(new_sp)
    except Exception as ex:
        print(f"[Sales Person Rename Sync Error] {ex}")

    return renamed_results


def _ensure_sales_person_has_territory_code(opener, sp_name, terr_code, headers_json, is_group=0):
    """
    When a leaf Territory Code (e.g. 'AD100') is encoded and assigned to a leaf Sales Person
    without a parenthesized code yet (e.g. 'JOSHUA TAN'), renames the Sales Person in ERPNext
    to 'JOSHUA TAN (AD100)' so subsequent Territory renames ('AD100' -> 'AD1002') automatically
    update the code inside the parentheses ('JOSHUA TAN (AD1002)').
    Never alters group folders or double-wraps an existing code.
    """
    clean_sp = safe_str(sp_name)
    clean_code = safe_str(terr_code)
    if not opener or not clean_sp or not clean_code or int(is_group or 0):
        return clean_sp
    if clean_sp.lower() in ("unassigned", "unassigned rep", "unassigned slot", "vacant", "folder (group)", "sales team"):
        return clean_sp
    if clean_code.lower() in ("all territories", "sales team"):
        return clean_sp
    # Already contains this territory code in parentheses
    if re.search(r"\(\s*" + re.escape(clean_code) + r"\s*\)", clean_sp, re.IGNORECASE):
        return clean_sp
    # Only append automatically when Sales Person has NO parenthesized territory code yet
    if re.search(r"\([^)]+\)\s*$", clean_sp):
        return clean_sp

    # Never rename group Sales Persons (e.g. District / Program folders)
    try:
        sp_doc = _find_existing_sales_person(opener, clean_sp, headers_json)
        if sp_doc and int(sp_doc.get("is_group") or 0):
            return clean_sp
    except Exception:
        pass

    target_sp = f"{clean_sp} ({clean_code})"
    # Collision guard: if target already exists, reuse it cleanly without overwriting
    existing_target = _find_existing_sales_person(opener, target_sp, headers_json)
    if existing_target:
        return safe_str(existing_target.get("name")) or target_sp

    try:
        sp_form = urllib.parse.urlencode({
            "doctype": "Sales Person",
            "old_name": clean_sp,
            "new_name": target_sp
        }).encode("utf-8")
        sp_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.rename_doc",
            data=sp_form,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        sp_res = call_erpnext_resiliently(opener, sp_req, timeout=12)
        if sp_res and sp_res.status == 200:
            try:
                sp_put = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(target_sp, safe='')}",
                    data=json.dumps({"sales_person_name": target_sp}).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                )
                call_erpnext_resiliently(opener, sp_put, timeout=10)
            except Exception:
                pass
            if "live_sales_persons" in st.session_state and isinstance(st.session_state.live_sales_persons, list):
                for s in st.session_state.live_sales_persons:
                    if not isinstance(s, dict):
                        continue
                    if s.get("name") == clean_sp or s.get("sales_person_name") == clean_sp:
                        s["name"] = target_sp
                        s["sales_person_name"] = target_sp
                    if s.get("parent_sales_person") == clean_sp:
                        s["parent_sales_person"] = target_sp
            return target_sp
    except Exception as ex:
        print(f"[Sales Person Auto-Tag Notice] {clean_sp} -> {target_sp}: {ex}")

    return clean_sp


def _resolve_sales_person_for_manager(opener, rep_name, headers_json):
    """
    Defensively resolves territory manager string to exact Sales Person DocType name on ERPNext.
    ERPNext stores sales persons as e.g. 'JAMES ANTHONY SOLIMAN (ADC02)'.
    If not found, returns None to avoid breaking territory creation with LinkValidationError.
    """
    if not rep_name or not opener:
        return None
    clean = safe_str(rep_name)
    if not clean or clean.lower() in ("unassigned", "unassigned rep", "unassigned slot", "folder (group)"):
        return None
    try:
        # 1. Exact match on primary key (name)
        chk_url = f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(clean, safe='')}"
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
    clean = safe_str(uid).lower()
    if not clean or not opener or "@" not in clean:
        return None
    try:
        u_url = f"{ERPNEXT_SERVER_URL}/api/resource/User/{urllib.parse.quote(clean)}"
        r = call_erpnext_resiliently(opener, urllib.request.Request(u_url, headers=headers_json), timeout=5)
        if r.status in [200, 201]:
            return clean
    except Exception:
        pass
    return None


def _resolve_medrep_user_id_from_sales_person(opener, sp_name, headers_json):
    """
    Resolves the logged-in MedRep's authoritative ERPNext User email from Sales Person -> Employee -> user_id
    so the HCP App and Territory Reconfig Web App stay 100% synchronized on territory availability.
    """
    clean_sp = safe_str(sp_name)
    if not clean_sp or not opener:
        return None
    try:
        sp_doc = _find_existing_sales_person(opener, clean_sp, headers_json)
        if not isinstance(sp_doc, dict):
            return None
        emp_id = safe_str(sp_doc.get("employee"))
        if not emp_id:
            return None
        emp_url = f"{ERPNEXT_SERVER_URL}/api/resource/Employee/{urllib.parse.quote(emp_id, safe='')}"
        e_res = call_erpnext_resiliently(opener, urllib.request.Request(emp_url, headers=headers_json), timeout=6)
        emp_doc = json.loads(e_res.read().decode("utf-8")).get("data", {})
        if not isinstance(emp_doc, dict):
            return None
        for cand in (emp_doc.get("user_id"), emp_doc.get("company_email"), emp_doc.get("personal_email")):
            resolved = _resolve_user_id(opener, cand, headers_json)
            if resolved:
                return resolved
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
            return "error", str(sve)

        def _sync_district_to_sales_person(mgr_name, dist_val, prog_val=""):
            clean_mgr = safe_str(mgr_name)
            clean_dist = safe_str(dist_val)
            if not clean_mgr:
                return
            if clean_dist:
                try:
                    call_erpnext_resiliently(opener, urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person/{urllib.parse.quote(clean_mgr, safe='')}",
                        data=json.dumps({"custom_district": clean_dist}).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    ), timeout=6)
                except Exception:
                    pass
                record_shared_sales_person_meta(
                    clean_mgr,
                    district=clean_dist,
                    program=prog_val if prog_val else None,
                    pending_erp_sync=False
                )

        def _resolve_or_autocreate_manager(mgr_name, parent_hint="", is_group_flag=0, dist_val="", prog_val=""):
            clean_mgr = safe_str(mgr_name)
            if not clean_mgr or clean_mgr.lower() in ("unassigned", "unassigned rep", "unassigned slot", "vacant", "folder (group)"):
                return None
            resolved = _resolve_sales_person_for_manager(opener, clean_mgr, headers_json)
            if resolved:
                if dist_val:
                    _sync_district_to_sales_person(resolved, dist_val, prog_val)
                return resolved
            sp_parent = safe_str(parent_hint)
            if not sp_parent or sp_parent == "All Territories":
                sp_parent = ""
            sp_ok, created_sp, _ = _ensure_sales_person_exists_in_erpnext(
                opener,
                clean_mgr,
                headers_json,
                parent_sp=sp_parent,
                is_group=int(is_group_flag or 0),
                district=dist_val,
                program=prog_val
            )
            return created_sp if sp_ok and created_sp else None

        def _create_single_territory_record(t_name, parent, is_group, t_mgr, custom_uid, custom_prog, custom_district="", parent_sp_hint=""):
            _ensure_district_custom_fields(opener, headers_json)
            p_ok, resolved_parent, p_err = _ensure_parent_territory_is_group(opener, parent, headers_json)
            effective_parent = resolved_parent or safe_str(parent) or "All Territories"
            resolved_mgr = _resolve_or_autocreate_manager(
                t_mgr,
                parent_hint=parent_sp_hint,
                is_group_flag=is_group,
                dist_val=custom_district,
                prog_val=custom_prog
            ) if t_mgr else None
            if resolved_mgr and not int(is_group or 0) and t_name:
                resolved_mgr = _ensure_sales_person_has_territory_code(opener, resolved_mgr, t_name, headers_json, is_group=is_group)
            resolved_uid = _resolve_user_id(opener, custom_uid, headers_json) if (custom_uid and resolved_mgr) else None
            if resolved_mgr and not resolved_uid:
                resolved_uid = _resolve_medrep_user_id_from_sales_person(opener, resolved_mgr, headers_json)

            body = {
                "territory_name": t_name,
                "parent_territory": effective_parent,
                "is_group": is_group
            }
            if resolved_mgr:
                body["territory_manager"] = resolved_mgr
            if resolved_uid:
                body["custom_user_id"] = resolved_uid
            elif not resolved_mgr:
                body["custom_user_id"] = ""
            if custom_prog:
                body["custom_account_or_program"] = custom_prog
            if safe_str(custom_district):
                body["custom_district"] = safe_str(custom_district)

            last_err = p_err if not p_ok else ""

            def _post_or_put_terr(p_body):
                data_bytes = json.dumps(p_body).encode("utf-8")
                req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                    data=data_bytes,
                    headers=headers_json,
                    method="POST"
                )
                try:
                    res = call_erpnext_resiliently(opener, req, timeout=12)
                    return res.status in [200, 201], ""
                except urllib.error.HTTPError as he:
                    err_msg = _extract_erp_http_error(he)
                    if "DuplicateEntryError" in err_msg:
                        up_req = urllib.request.Request(
                            f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(t_name, safe='')}",
                            data=data_bytes,
                            headers=headers_json,
                            method="PUT"
                        )
                        try:
                            ur = call_erpnext_resiliently(opener, up_req, timeout=12)
                            return ur.status in [200, 201], ""
                        except urllib.error.HTTPError as uhe:
                            return False, _extract_erp_http_error(uhe)
                        except Exception as uex:
                            return False, str(uex)
                    return False, err_msg
                except Exception as ex:
                    return False, str(ex)

            success, err = _post_or_put_terr(body)
            if not success:
                last_err = err or last_err
                # Progressive schema-safe fallback: strip custom_account_or_program FIRST so custom_user_id (HCP App MedRep sync) stays intact!
                for opt_fields in (
                    ["custom_account_or_program"],
                    ["custom_district"],
                    ["custom_user_id"],
                    ["territory_manager"]
                ):
                    removed_any = False
                    for lf in opt_fields:
                        if lf in body:
                            body.pop(lf, None)
                            removed_any = True
                    if removed_any:
                        success, err = _post_or_put_terr(body)
                        if success:
                            break
                        last_err = err or last_err

            # Fallback: Frappe native TreeView add_node endpoint (/app/territory/view/tree)
            if not success:
                try:
                    tv_parent = body.get("parent_territory") or effective_parent
                    form_data = urllib.parse.urlencode({
                        "doctype": "Territory",
                        "parent": tv_parent,
                        "territory_name": t_name,
                        "is_group": str(int(is_group or 0)),
                        "is_root": "false"
                    }).encode("utf-8")
                    tv_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/method/frappe.desk.treeview.add_node",
                        data=form_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                        method="POST"
                    )
                    tv_res = call_erpnext_resiliently(opener, tv_req, timeout=12)
                    if tv_res.status in [200, 201]:
                        success = True
                except urllib.error.HTTPError as tv_he:
                    last_err = _extract_erp_http_error(tv_he) or last_err
                except Exception as tv_ex:
                    last_err = str(tv_ex) or last_err

            # Fallback: Frappe Desk frappe.client.insert RPC
            if not success:
                try:
                    ins_doc = {
                        "doctype": "Territory",
                        "territory_name": t_name,
                        "parent_territory": body.get("parent_territory") or effective_parent,
                        "is_group": int(is_group or 0)
                    }
                    ins_data = urllib.parse.urlencode({"doc": json.dumps(ins_doc)}).encode("utf-8")
                    ins_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/method/frappe.client.insert",
                        data=ins_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                        method="POST"
                    )
                    ins_res = call_erpnext_resiliently(opener, ins_req, timeout=12)
                    if ins_res.status in [200, 201]:
                        success = True
                except urllib.error.HTTPError as ins_he:
                    last_err = _extract_erp_http_error(ins_he) or last_err
                except Exception as ins_ex:
                    last_err = str(ins_ex) or last_err

            # Ensure critical HCP App MedRep sync fields (territory_manager, custom_user_id, custom_district) are applied even after fallback creation
            if success and (resolved_mgr or safe_str(custom_district) or resolved_uid):
                extra_put = {}
                if resolved_mgr:
                    extra_put["territory_manager"] = resolved_mgr
                if resolved_uid:
                    extra_put["custom_user_id"] = resolved_uid
                if safe_str(custom_district):
                    extra_put["custom_district"] = safe_str(custom_district)
                if extra_put:
                    put_url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(t_name, safe='')}"
                    try:
                        call_erpnext_resiliently(opener, urllib.request.Request(
                            put_url,
                            data=json.dumps(extra_put).encode("utf-8"),
                            headers=headers_json,
                            method="PUT"
                        ), timeout=8)
                    except Exception:
                        # Apply each critical field independently so one missing custom field never drops territory_manager or custom_user_id
                        for fk, fv in extra_put.items():
                            try:
                                call_erpnext_resiliently(opener, urllib.request.Request(
                                    put_url,
                                    data=json.dumps({fk: fv}).encode("utf-8"),
                                    headers=headers_json,
                                    method="PUT"
                                ), timeout=6)
                            except Exception:
                                pass

            if success and "live_territories" in st.session_state and isinstance(st.session_state["live_territories"], list):
                if not any(t.get("name") == t_name for t in st.session_state["live_territories"]):
                    new_live_row = {
                        "name": t_name,
                        "territory_name": t_name,
                        "parent_territory": effective_parent,
                        "is_group": is_group,
                        "territory_manager": resolved_mgr or "",
                        "custom_user_id": resolved_uid or "",
                        "custom_account_or_program": custom_prog or ""
                    }
                    if safe_str(custom_district):
                        new_live_row["custom_district"] = safe_str(custom_district)
                        new_live_row["district"] = safe_str(custom_district)
                    st.session_state["live_territories"].append(new_live_row)
            return success, ("" if success else (last_err or f"ERPNext rejected creation of Territory '{t_name}'."))

        def _edit_single_territory_record(orig_name, new_parent, new_is_group, new_mgr, custom_uid="", custom_prog="", explicit_status=None, custom_district=None):
            if not orig_name:
                return "error", "Territory original name is missing."
            _ensure_district_custom_fields(opener, headers_json)
            if new_parent and new_parent != "All Territories":
                _ensure_parent_territory_is_group(opener, new_parent, headers_json)

            clean_dist = safe_str(custom_district) if custom_district is not None else ""
            is_unassigned_mgr = (not new_mgr) or new_mgr.lower() in ("unassigned", "unassigned rep", "unassigned slot", "vacant", "folder (group)")
            resolved_mgr = _resolve_or_autocreate_manager(
                new_mgr,
                parent_hint="",
                is_group_flag=new_is_group,
                dist_val=clean_dist,
                prog_val=custom_prog
            ) if not is_unassigned_mgr else None
            resolved_uid = _resolve_user_id(opener, custom_uid, headers_json) if custom_uid else None

            if explicit_status in ("Active", "Vacant", "Inactive"):
                eff_status = explicit_status
            else:
                eff_status = "Active" if ((not is_unassigned_mgr) or new_is_group) else "Vacant"

            if eff_status in ("Vacant", "Inactive") or is_unassigned_mgr:
                resolved_uid = ""
            else:
                if resolved_mgr and not int(new_is_group or 0) and orig_name:
                    resolved_mgr = _ensure_sales_person_has_territory_code(opener, resolved_mgr, orig_name, headers_json, is_group=new_is_group)
                if not resolved_uid and resolved_mgr:
                    resolved_uid = _resolve_medrep_user_id_from_sales_person(opener, resolved_mgr, headers_json) or ""

            shared_mgr = "" if (is_unassigned_mgr or eff_status in ("Vacant", "Inactive")) else (resolved_mgr or new_mgr)

            body = {}
            if new_parent:
                body["parent_territory"] = new_parent
            if new_is_group is not None:
                body["is_group"] = int(new_is_group or 0)
            if eff_status in ("Vacant", "Inactive") or is_unassigned_mgr:
                # HCP App Sync Invariant: Vacating or deactivating a territory MUST clear BOTH territory_manager & custom_user_id
                body["territory_manager"] = ""
                body["custom_user_id"] = ""
            elif resolved_mgr:
                body["territory_manager"] = resolved_mgr
                body["custom_user_id"] = resolved_uid or (custom_uid if (custom_uid and "@" in custom_uid) else "")
            elif new_mgr:
                body["territory_manager"] = new_mgr
                body["custom_user_id"] = resolved_uid or (custom_uid if (custom_uid and "@" in custom_uid) else "")

            if custom_prog:
                body["custom_account_or_program"] = custom_prog
            if custom_district is not None:
                body["custom_district"] = clean_dist

            def _put_terr(p_body):
                req = urllib.request.Request(
                    f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(orig_name, safe='')}",
                    data=json.dumps(p_body).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                )
                return call_erpnext_resiliently(opener, req, timeout=12)

            synced_ok = False
            last_err = ""
            try:
                res = _put_terr(body)
                if res.status == 200:
                    synced_ok = True
                    msg_out = ("success", f'Territory "{orig_name}" transferred/updated under "{new_parent or "All Territories"}" on {get_server_display_name()}!')
                else:
                    msg_out = ("warning", f"ERPNext responded with HTTP {res.status}")
            except urllib.error.HTTPError as he:
                last_err = _extract_erp_http_error(he)
                # Progressive schema-safe fallback: strip custom_account_or_program FIRST while keeping custom_user_id (HCP App MedRep sync) intact!
                for strip_keys in (
                    ["custom_account_or_program"],
                    ["custom_district"],
                    ["custom_user_id"],
                    ["territory_manager"]
                ):
                    removed = False
                    for lf in strip_keys:
                        if lf in body:
                            body.pop(lf, None)
                            removed = True
                    if not removed:
                        continue
                    try:
                        res = _put_terr(body)
                        if res.status == 200:
                            synced_ok = True
                            msg_out = ("success", f'Territory "{orig_name}" transferred/updated under "{new_parent or "All Territories"}" on {get_server_display_name()}!')
                            break
                    except urllib.error.HTTPError as he_step:
                        last_err = _extract_erp_http_error(he_step) or last_err
                        if he_step.code == 404:
                            c_ok, c_err = _create_single_territory_record(
                                orig_name,
                                new_parent or "All Territories",
                                int(new_is_group or 0),
                                resolved_mgr or "",
                                resolved_uid or "",
                                custom_prog,
                                custom_district=clean_dist
                            )
                            if c_ok:
                                synced_ok = True
                                msg_out = ("success", f'Territory "{orig_name}" created & linked under "{new_parent or "All Territories"}" on {get_server_display_name()}!')
                            else:
                                last_err = c_err or last_err
                            break
                if not synced_ok and 'msg_out' not in locals():
                    msg_out = ("error", f'Could not update Territory "{orig_name}" on {get_server_display_name()}: {last_err or "ERPNext rejected update."}')
            except Exception as ex:
                msg_out = ("error", f'Could not update Territory "{orig_name}" on {get_server_display_name()}: {str(ex)}')

            record_shared_territory_edit(
                orig_name,
                parent=new_parent if new_parent else None,
                is_group=new_is_group,
                manager=shared_mgr,
                user_id=(resolved_uid or custom_uid) if custom_uid else None,
                program=custom_prog if custom_prog else None,
                status=eff_status,
                district=clean_dist if custom_district is not None else None,
                pending_erp_sync=(not synced_ok)
            )
            return msg_out

        def _rename_single_territory_record(old_name, new_name, parent_terr="Abbott DC Territories", assigned_mgr="", prev_terr=""):
            if not old_name or not new_name:
                return False, "Both old and new names are required to rename.", []

            def _extract_erp_http_err(http_err):
                try:
                    body_txt = http_err.read().decode("utf-8", errors="ignore")
                    body_json = json.loads(body_txt) if body_txt else {}
                    msg_val = body_json.get("exception") or body_json.get("message")
                    if not msg_val and body_json.get("_server_messages"):
                        msgs = json.loads(body_json["_server_messages"])
                        if msgs:
                            m_obj = json.loads(msgs[0]) if isinstance(msgs[0], str) else msgs[0]
                            msg_val = m_obj.get("message")
                    return msg_val or body_txt or f"HTTP Error {http_err.code}"
                except Exception:
                    return f"HTTP Error {http_err.code}"

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
            res = None
            rename_err_msg = ""
            try:
                res = call_erpnext_resiliently(opener, req, timeout=12)
            except urllib.error.HTTPError as he:
                rename_err_msg = _extract_erp_http_err(he)
                low_err = rename_err_msg.lower()
                if he.code != 404 and "does not exist" not in low_err and "not found" not in low_err:
                    return False, f"ERPNext: {rename_err_msg}", []

            renamed = False
            if res and res.status == 200:
                renamed = True
                try:
                    put_data = json.dumps({"territory_name": new_name}).encode("utf-8")
                    put_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(new_name, safe='')}",
                        data=put_data,
                        headers=headers_json,
                        method="PUT"
                    )
                    call_erpnext_resiliently(opener, put_req, timeout=10)
                except Exception:
                    pass
            else:
                # If old_name was a local/baseline territory not yet present in ERPNext, register new_name directly
                try:
                    if parent_terr and parent_terr != "All Territories":
                        _ensure_parent_territory_is_group(opener, parent_terr, headers_json)
                    c_data = json.dumps({
                        "territory_name": new_name,
                        "parent_territory": parent_terr or "All Territories",
                        "is_group": 0
                    }).encode("utf-8")
                    c_req = urllib.request.Request(
                        f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                        data=c_data,
                        headers=headers_json,
                        method="POST"
                    )
                    c_res = call_erpnext_resiliently(opener, c_req, timeout=12)
                    if c_res and c_res.status in [200, 201]:
                        renamed = True
                except urllib.error.HTTPError as che:
                    rename_err_msg = _extract_erp_http_err(che) or rename_err_msg
                except Exception as cex:
                    rename_err_msg = str(cex) or rename_err_msg

            if not renamed:
                return False, f"ERPNext: {rename_err_msg or f'Could not rename {old_name} to {new_name}'}", []

            record_shared_territory_rename(old_name, new_name)

            # Synchronize Sales Person parenthesized territory code (e.g. 'MEDREP (OLD)' -> 'MEDREP (NEW)')
            renamed_sps = _sync_sales_person_code_on_territory_rename(
                opener,
                old_name,
                new_name,
                headers_json,
                assigned_mgr=assigned_mgr,
                prev_terr=prev_terr
            )

            # Update session state live_territories in-memory immediately to prevent revert
            if "live_territories" in st.session_state and isinstance(st.session_state.live_territories, list):
                found = False
                for t in st.session_state.live_territories:
                    if t.get("name") == old_name or t.get("territory_name") == old_name:
                        t["name"] = new_name
                        t["territory_name"] = new_name
                        if renamed_sps and safe_str(t.get("territory_manager")):
                            updated_tm = _replace_parenthesized_territory_code(t.get("territory_manager"), old_name, new_name)
                            if updated_tm:
                                t["territory_manager"] = updated_tm
                        found = True
                        break
                if not found:
                    st.session_state.live_territories.append({
                        "name": new_name,
                        "territory_name": new_name,
                        "parent_territory": parent_terr or "All Territories",
                        "is_group": 0
                    })

            return True, "", renamed_sps

        if action == "tree_add":
            t_name = safe_str(payload.get("territory_name"))
            parent = safe_str(payload.get("parent_territory")) or "All Territories"
            is_group = int(payload.get("is_group", 0) or 0)
            t_mgr = safe_str(payload.get("territory_manager"))
            custom_uid = safe_str(payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"))
            custom_prog = safe_str(payload.get("custom_account_or_program") or payload.get("program"))
            custom_dist = safe_str(payload.get("custom_district") or payload.get("district_area") or payload.get("area_district"))
            sp_parent_hint = safe_str(payload.get("parent_sales_person")) or ""
            if not t_name:
                return "error", "Territory name cannot be blank."
            ok, err_msg = _create_single_territory_record(
                t_name,
                parent,
                is_group,
                t_mgr,
                custom_uid,
                custom_prog,
                custom_district=custom_dist,
                parent_sp_hint=sp_parent_hint
            )
            if ok:
                return "success", f'Territory "{t_name}" created & synchronized with {get_server_display_name()}!'
            return "error", f'Could not create Territory "{t_name}" on {get_server_display_name()}: {err_msg}'

        elif action == "bulk_tree_add":
            terrs = payload.get("territories", [])
            count = 0
            errors = []
            for item in terrs:
                if isinstance(item, dict):
                    t_name = safe_str(item.get("territory_name") or item.get("name") or item.get("code"))
                    parent = safe_str(item.get("parent_territory") or item.get("district")) or "All Territories"
                    is_group = int(item.get("is_group", 0) or 0)
                    t_mgr = safe_str(item.get("territory_manager") or item.get("rep"))
                    uid = safe_str(item.get("custom_user_id") or item.get("user_id") or item.get("userId"))
                    prog = safe_str(item.get("custom_account_or_program") or item.get("program"))
                    item_dist = safe_str(item.get("custom_district") or item.get("district_area") or item.get("area_district"))
                    sp_parent_hint = safe_str(item.get("parent_sales_person")) or ""
                    if t_name:
                        ok, err_msg = _create_single_territory_record(
                            t_name,
                            parent,
                            is_group,
                            t_mgr,
                            uid,
                            prog,
                            custom_district=item_dist,
                            parent_sp_hint=sp_parent_hint
                        )
                        if ok:
                            count += 1
                        elif err_msg:
                            errors.append(f"{t_name}: {err_msg}")
            if count == 0 and errors:
                return "error", f"Could not create territories on {get_server_display_name()}: {errors[0]}"
            if errors:
                return "warning", f"Synced {count} territories to {get_server_display_name()}; {len(errors)} failed ({errors[0]})."
            return "success", f"Successfully synced {count} new territories live to {get_server_display_name()}!"

        elif action == "tree_edit":
            orig_name = safe_str(payload.get("name") or payload.get("territory_name") or payload.get("activeCode") or payload.get("code"))
            new_parent = safe_str(payload.get("parent_territory") or payload.get("district")) or "All Territories"
            new_is_group = int(payload.get("is_group", 0) or 0)
            new_mgr = safe_str(payload.get("territory_manager") or payload.get("rep"))
            custom_uid = safe_str(payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"))
            custom_prog = safe_str(payload.get("custom_account_or_program") or payload.get("program"))
            explicit_status = safe_str(payload.get("status") or payload.get("operational_status")) or None
            has_dist = any(k in payload for k in ("custom_district", "district_area", "area_district"))
            custom_dist = safe_str(payload.get("custom_district") or payload.get("district_area") or payload.get("area_district")) if has_dist else None
            return _edit_single_territory_record(orig_name, new_parent, new_is_group, new_mgr, custom_uid, custom_prog, explicit_status, custom_district=custom_dist)

        elif action == "bulk_tree_edit":
            items = payload.get("territories", [])
            updated_count = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                t_name = safe_str(item.get("name") or item.get("territory_name") or item.get("activeCode") or item.get("code"))
                if not t_name:
                    continue
                t_parent = safe_str(item.get("parent_territory") or item.get("district"))
                t_is_group = int(item.get("is_group", 0) or 0)
                t_mgr = safe_str(item.get("territory_manager") or item.get("rep"))
                t_uid = safe_str(item.get("custom_user_id") or item.get("user_id") or item.get("userId"))
                t_prog = safe_str(item.get("custom_account_or_program") or item.get("program"))
                t_status = safe_str(item.get("status") or item.get("operational_status")) or None
                has_dist = any(k in item for k in ("custom_district", "district_area", "area_district"))
                t_dist = safe_str(item.get("custom_district") or item.get("district_area") or item.get("area_district")) if has_dist else None
                st_code, _ = _edit_single_territory_record(t_name, t_parent, t_is_group, t_mgr, t_uid, t_prog, t_status, custom_district=t_dist)
                if st_code == "success":
                    updated_count += 1
            return "success", f"Bulk updated {updated_count} territories live on {get_server_display_name()}!"

        elif action == "tree_rename":
            old_name = safe_str(payload.get("old_name") or payload.get("territory_name") or payload.get("name"))
            new_name = safe_str(payload.get("new_name"))
            parent_terr = safe_str(payload.get("parent_territory") or "Abbott DC Territories")
            if not old_name or not new_name:
                return "error", "Both old and new names are required to rename."
            ok, err_msg, renamed_sps = _rename_single_territory_record(
                old_name,
                new_name,
                parent_terr=parent_terr,
                assigned_mgr=safe_str(payload.get("territory_manager")),
                prev_terr=safe_str(payload.get("prev_code"))
            )
            if not ok:
                return "warning", err_msg

            # If Grid Edit modal modified parent/manager/user/status alongside renaming the code, persist those fields too
            if payload.get("apply_field_updates"):
                edit_parent = safe_str(payload.get("parent_territory"))
                edit_is_group = int(payload.get("is_group", 0) or 0)
                edit_mgr = safe_str(payload.get("territory_manager"))
                # Prevent Grid Edit from reverting Territory.territory_manager back to the pre-rename Sales Person code (e.g. 'JOSHUA TAN (AD100)' -> 'JOSHUA TAN (AD1002)')
                if edit_mgr:
                    replaced_edit_mgr = _replace_parenthesized_territory_code(edit_mgr, old_name, new_name)
                    if replaced_edit_mgr:
                        edit_mgr = replaced_edit_mgr
                    elif renamed_sps:
                        edit_base = re.sub(r"\s*\([^)]*\)", "", edit_mgr).strip().lower()
                        for rsp in renamed_sps:
                            rsp_base = re.sub(r"\s*\([^)]*\)", "", safe_str(rsp)).strip().lower()
                            if edit_base and rsp_base == edit_base:
                                edit_mgr = safe_str(rsp)
                                break
                edit_uid = safe_str(payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"))
                edit_prog = safe_str(payload.get("custom_account_or_program") or payload.get("program"))
                edit_status = safe_str(payload.get("status") or payload.get("operational_status")) or None
                has_dist = any(k in payload for k in ("custom_district", "district_area", "area_district"))
                edit_dist = safe_str(payload.get("custom_district") or payload.get("district_area") or payload.get("area_district")) if has_dist else None
                _edit_single_territory_record(new_name, edit_parent, edit_is_group, edit_mgr, edit_uid, edit_prog, edit_status, custom_district=edit_dist)

            sp_suffix = f' (Synced Sales Person: {", ".join(renamed_sps)})' if renamed_sps else ""
            return "success", f'Renamed "{old_name}" -> "{new_name}"{sp_suffix} live on {get_server_display_name()}!'

        elif action == "bulk_tree_rename":
            items = payload.get("renames", [])
            renamed_count = 0
            all_synced_sps = []
            errors = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                old_n = safe_str(item.get("old_name") or item.get("name"))
                new_n = safe_str(item.get("new_name"))
                if not old_n or not new_n or old_n == new_n:
                    continue
                ok, err_msg, sps = _rename_single_territory_record(
                    old_n,
                    new_n,
                    parent_terr=safe_str(item.get("parent_territory") or "Abbott DC Territories"),
                    assigned_mgr=safe_str(item.get("territory_manager") or item.get("rep")),
                    prev_terr=safe_str(item.get("prev_code"))
                )
                if ok:
                    renamed_count += 1
                    all_synced_sps.extend(sps)
                elif err_msg:
                    errors.append(f"{old_n}: {err_msg}")
            if renamed_count == 0 and errors:
                return "warning", errors[0]
            sp_suffix = f" & synced {len(all_synced_sps)} Sales Person code(s)" if all_synced_sps else ""
            return "success", f"Bulk renamed {renamed_count} territories{sp_suffix} live on {get_server_display_name()}!"

        elif action == "tree_delete":
            name = safe_str(payload.get("name") or payload.get("territory_name") or payload.get("territory"))
            if not name:
                return "error", "Territory name is required to delete."
            record_shared_territory_deletion(name)
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(name, safe='')}",
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                method="DELETE"
            )
            res = call_erpnext_resiliently(opener, req, timeout=12)
            if res.status in [200, 202]:
                return "success", f'Territory "{name}" deleted from {get_server_display_name()}!'
            return "warning", f"ERPNext responded with HTTP {res.status}"

        elif action in ["territory_toggle_status", "territory_deactivate"]:
            t_name = safe_str(payload.get("territory") or payload.get("territory_name") or payload.get("name") or payload.get("code") or payload.get("activeCode"))
            new_mgr = safe_str(payload.get("territory_manager") or payload.get("rep"))
            new_uid = safe_str(payload.get("custom_user_id") or payload.get("user_id") or payload.get("userId"))
            new_status = safe_str(payload.get("status") or payload.get("operational_status") or ("Active" if new_mgr and "INACTIVE" not in new_mgr.upper() and "UNASSIGNED" not in new_mgr.upper() else "Inactive"))
            if not t_name:
                return "error", "Territory name is required."
            resolved_mgr = _resolve_sales_person_for_manager(opener, new_mgr, headers_json) if (new_status == "Active" and new_mgr) else None
            if new_status in ("Vacant", "Inactive"):
                erp_mgr = ""
                erp_uid = ""
            else:
                erp_mgr = resolved_mgr or new_mgr
                erp_uid = _resolve_user_id(opener, new_uid, headers_json) if new_uid else ""
                if not erp_uid and resolved_mgr:
                    erp_uid = _resolve_medrep_user_id_from_sales_person(opener, resolved_mgr, headers_json) or ""
            if new_status != "Active" or erp_mgr:
                # HCP App Sync Invariant: Keep Territory.territory_manager and Territory.custom_user_id strictly synchronized
                body = {"territory_manager": erp_mgr, "custom_user_id": erp_uid}
                put_url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(t_name, safe='')}"
                try:
                    res = call_erpnext_resiliently(opener, urllib.request.Request(
                        put_url,
                        data=json.dumps(body).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    ), timeout=12)
                    if res.status == 200:
                        return "success", f'Territory "{t_name}" status set to {new_status} on {get_server_display_name()}!'
                    return "warning", f"ERPNext responded with HTTP {res.status}"
                except urllib.error.HTTPError as he:
                    # Fallback if custom_user_id field is absent on target schema
                    try:
                        res2 = call_erpnext_resiliently(opener, urllib.request.Request(
                            put_url,
                            data=json.dumps({"territory_manager": erp_mgr}).encode("utf-8"),
                            headers=headers_json,
                            method="PUT"
                        ), timeout=12)
                        if res2.status == 200:
                            return "success", f'Territory "{t_name}" status set to {new_status} on {get_server_display_name()}!'
                    except urllib.error.HTTPError as he2:
                        return "error", f'Could not update Territory "{t_name}" status on {get_server_display_name()}: {_extract_erp_http_error(he2)}'
                    return "error", f'Could not update Territory "{t_name}" status on {get_server_display_name()}: {_extract_erp_http_error(he)}'
                except Exception as ex:
                    return "error", f'Could not update Territory "{t_name}" status on {get_server_display_name()}: {str(ex)}'
            return "success", f'Territory "{t_name}" status set to {new_status}!'

        elif action in ["bulk_decommission", "bulk_archive"]:
            items = payload.get("territories", [])
            updated_count = 0
            errors = []
            for item in items:
                if isinstance(item, str):
                    t_name = safe_str(item)
                elif isinstance(item, dict):
                    t_name = safe_str(item.get("territory") or item.get("name") or item.get("code") or item.get("activeCode"))
                else:
                    continue
                if not t_name:
                    continue
                put_url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(t_name, safe='')}"
                # Clear BOTH territory_manager and custom_user_id so archived MedReps immediately lose territory availability in HCP App
                try:
                    res = call_erpnext_resiliently(opener, urllib.request.Request(
                        put_url,
                        data=json.dumps({"territory_manager": "", "custom_user_id": ""}).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    ), timeout=10)
                    if res.status == 200:
                        updated_count += 1
                except urllib.error.HTTPError:
                    try:
                        res2 = call_erpnext_resiliently(opener, urllib.request.Request(
                            put_url,
                            data=json.dumps({"territory_manager": ""}).encode("utf-8"),
                            headers=headers_json,
                            method="PUT"
                        ), timeout=10)
                        if res2.status == 200:
                            updated_count += 1
                    except Exception as ex2:
                        errors.append(f"{t_name}: {str(ex2)}")
                except Exception as ex:
                    errors.append(f"{t_name}: {str(ex)}")
            if updated_count == 0 and errors:
                return "error", f"Could not archive territories on {get_server_display_name()}: {errors[0]}"
            return "success", f"Archived {updated_count} territories as Inactive on {get_server_display_name()}!"

        elif action == "resignation_handover":
            t_name = safe_str(payload.get("territory") or payload.get("name") or payload.get("territory_name"))
            new_rep = safe_str(payload.get("new_rep") or payload.get("territory_manager"))
            new_uid = safe_str(payload.get("new_user_id") or payload.get("custom_user_id"))
            if not t_name:
                return "error", "Territory name is required for handover."
            resolved_mgr = _resolve_sales_person_for_manager(opener, new_rep, headers_json) if new_rep else None
            if resolved_mgr and t_name:
                resolved_mgr = _ensure_sales_person_has_territory_code(opener, resolved_mgr, t_name, headers_json, is_group=0)
            resolved_uid = _resolve_user_id(opener, new_uid, headers_json) if new_uid else None
            if not resolved_uid and resolved_mgr:
                resolved_uid = _resolve_medrep_user_id_from_sales_person(opener, resolved_mgr, headers_json)
            shared_mgr = resolved_mgr or new_rep
            # Always overwrite custom_user_id so resigned MedRep immediately loses HCP App territory availability
            body = {"territory_manager": shared_mgr, "custom_user_id": resolved_uid or ""}
            put_url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(t_name, safe='')}"
            try:
                res = call_erpnext_resiliently(opener, urllib.request.Request(
                    put_url,
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers_json,
                    method="PUT"
                ), timeout=12)
                if res.status == 200:
                    return "success", f'Handover saved: "{t_name}" reassigned to "{shared_mgr}" on {get_server_display_name()}!'
                return "warning", f"ERPNext responded with HTTP {res.status}"
            except urllib.error.HTTPError as he:
                try:
                    res2 = call_erpnext_resiliently(opener, urllib.request.Request(
                        put_url,
                        data=json.dumps({"territory_manager": shared_mgr}).encode("utf-8"),
                        headers=headers_json,
                        method="PUT"
                    ), timeout=12)
                    if res2.status == 200:
                        return "success", f'Handover saved: "{t_name}" reassigned to "{shared_mgr}" on {get_server_display_name()}!'
                except Exception:
                    pass
                return "error", f'Handover failed for "{t_name}" on {get_server_display_name()}: {_extract_erp_http_error(he)}'
            except Exception as ex:
                return "error", f'Handover failed for "{t_name}" on {get_server_display_name()}: {str(ex)}'

        elif action == "sales_person_create":
            sp_name = safe_str(payload.get("sales_person_name") or payload.get("name"))
            parent_sp = safe_str(payload.get("parent_sales_person")) or "Sales Team"
            grand_parent_sp = safe_str(payload.get("grand_parent_sales_person")) or ""
            is_group = int(payload.get("is_group", 0) or 0)
            enabled = int(payload.get("enabled", 1) if payload.get("enabled") is not None else 1)
            emp = safe_str(payload.get("employee"))
            district = safe_str(payload.get("custom_district") or payload.get("district"))
            dept = safe_str(payload.get("department"))
            prog = safe_str(payload.get("custom_account_or_program") or payload.get("program"))
            comm = payload.get("commission_rate")
            targets = payload.get("targets")

            if not sp_name:
                return "error", "Sales Person Name cannot be blank."

            ok, created_name, err_msg = _ensure_sales_person_exists_in_erpnext(
                opener,
                sp_name,
                headers_json,
                parent_sp=parent_sp,
                is_group=is_group,
                employee=emp,
                district=district,
                department=dept,
                enabled=enabled,
                commission_rate=comm,
                targets=targets,
                program=prog,
                grand_parent_sp=grand_parent_sp
            )

            resolved_parent = parent_sp
            if ok and created_name:
                live_parent_doc = _find_existing_sales_person(opener, created_name, headers_json)
                if live_parent_doc and safe_str(live_parent_doc.get("parent_sales_person")):
                    resolved_parent = safe_str(live_parent_doc.get("parent_sales_person"))

            # Refresh session state live_sales_persons immediately (including any newly auto-created parent folder)
            new_sp_entry = {
                "name": created_name or sp_name,
                "sales_person_name": created_name or sp_name,
                "parent_sales_person": resolved_parent,
                "employee": emp or None,
                "is_group": is_group,
                "enabled": enabled,
                "department": dept or None,
                "custom_district": district or "",
                "district": district or "",
                "custom_account_or_program": prog or "",
                "program": prog or ""
            }
            if ok:
                live_sps = fetch_live_sales_persons(opener)
                if isinstance(live_sps, list) and len(live_sps) > 0:
                    st.session_state["live_sales_persons"] = live_sps
                elif "live_sales_persons" in st.session_state and isinstance(st.session_state.live_sales_persons, list):
                    idx = next((i for i, s in enumerate(st.session_state.live_sales_persons) if s.get("name") == new_sp_entry["name"]), -1)
                    if idx >= 0:
                        st.session_state.live_sales_persons[idx] = new_sp_entry
                    else:
                        st.session_state.live_sales_persons.insert(0, new_sp_entry)
                else:
                    st.session_state["live_sales_persons"] = [new_sp_entry]

                dist_suffix = f' (District: {district})' if district else ''
                parent_suffix = f' under "{resolved_parent}"' if resolved_parent else ''
                return "success", f'Sales Person "{created_name or sp_name}" created{parent_suffix}{dist_suffix} on {get_server_display_name()}!'

            return "error", f'Could not create Sales Person "{sp_name}" on {get_server_display_name()}: {err_msg}'

        elif action == "employee_create":
            first_name = safe_str(payload.get("first_name"))
            last_name = safe_str(payload.get("last_name"))
            gender = safe_str(payload.get("gender")) or "Male"
            dob = safe_str(payload.get("date_of_birth")) or "1995-01-01"
            doj = safe_str(payload.get("date_of_joining")) or "2024-01-01"
            company = safe_str(payload.get("company")) or "Professional Insights Marketing Services"
            status = safe_str(payload.get("status")) or "Active"
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
                body["middle_name"] = safe_str(payload.get("middle_name"))
            if payload.get("designation"):
                body["designation"] = safe_str(payload.get("designation"))
            if payload.get("department"):
                body["department"] = safe_str(payload.get("department"))
            if payload.get("reports_to"):
                body["reports_to"] = safe_str(payload.get("reports_to"))
            if payload.get("cell_number"):
                body["cell_number"] = safe_str(payload.get("cell_number"))
            if payload.get("company_email"):
                body["company_email"] = safe_str(payload.get("company_email"))

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

def _sync_live_masterlists(opener, core_only=False):
    """Fetches live ERPNext DocTypes in parallel; preserves prior valid data on transient network failures."""
    core_specs = {
        "live_territories": fetch_live_territories,
        "live_sales_persons": fetch_live_sales_persons,
        "live_employees": fetch_live_employees,
        "live_users": fetch_live_users,
        "live_hcp_accounts": fetch_live_hcp_accounts,
    }
    full_specs = {
        **core_specs,
        "live_institutions": fetch_live_institutions,
        "live_item_groups": fetch_live_item_groups,
        "live_fiscal_years": fetch_live_fiscal_years,
        "live_distributions": fetch_live_distributions,
        "live_departments": fetch_live_departments,
        "live_designations": fetch_live_designations,
    }
    fetch_specs = core_specs if core_only else full_specs
    results = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = {key: executor.submit(fn, opener) for key, fn in fetch_specs.items()}
            for key, fut in futures.items():
                try:
                    val = fut.result()
                    if val is not None:
                        results[key] = val
                except Exception as f_ex:
                    print(f"[Streamlit Data Fetch Warning] {key}: {f_ex}")
    except Exception as ex:
        print(f"[Streamlit Data Fetch Warning] {ex}")
        for key, fn in fetch_specs.items():
            if key not in results:
                try:
                    val = fn(opener)
                    if val is not None:
                        results[key] = val
                except Exception as seq_ex:
                    print(f"[Streamlit Data Fetch Warning] {key} sequential: {seq_ex}")
    for key, val in results.items():
        st.session_state[key] = val

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
if "pending_reset_delivery" not in st.session_state:
    st.session_state["pending_reset_delivery"] = False
if "opener" not in st.session_state:
    st.session_state["opener"] = None

# Single-delivery auth and reset responses: deliver ONLY during the active dispatch cycle.
# On subsequent browser page refreshes (F5) or reboots, deliver None so the web app always opens cleanly on the Login Page!
auth_to_deliver = None
if st.session_state.get("pending_auth_delivery"):
    auth_to_deliver = st.session_state.get("auth_response")
    st.session_state["pending_auth_delivery"] = False

reset_to_deliver = None
if st.session_state.get("pending_reset_delivery"):
    reset_to_deliver = st.session_state.get("reset_password_response")
    st.session_state["pending_reset_delivery"] = False

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
if "live_hcp_accounts" not in st.session_state:
    st.session_state["live_hcp_accounts"] = None
if "live_item_groups" not in st.session_state:
    st.session_state["live_item_groups"] = None
if "live_fiscal_years" not in st.session_state:
    st.session_state["live_fiscal_years"] = None
if "live_distributions" not in st.session_state:
    st.session_state["live_distributions"] = None
if "live_departments" not in st.session_state:
    st.session_state["live_departments"] = None
if "live_designations" not in st.session_state:
    st.session_state["live_designations"] = None
if "tree_sync_event" not in st.session_state:
    st.session_state["tree_sync_event"] = None
if "last_action_timestamp" not in st.session_state:
    st.session_state["last_action_timestamp"] = 0

# Render the web app component directly (Opens directly to the native login view)
_active_prog = st.session_state.get("active_program", "Abbott Diabetes Care")
_accounts_for_prog = st.session_state.get(f"live_accounts_{_active_prog}")
if _accounts_for_prog is None:
    _accounts_for_prog = st.session_state.get("live_hcp_accounts")
component_val = portal_component(
    auth_response=auth_to_deliver,
    reset_password_response=reset_to_deliver,
    live_territories=st.session_state["live_territories"],
    live_sales_persons=st.session_state["live_sales_persons"],
    live_employees=st.session_state["live_employees"],
    live_users=st.session_state["live_users"],
    live_institutions=st.session_state["live_institutions"],
    live_accounts=_accounts_for_prog,
    live_item_groups=st.session_state["live_item_groups"],
    live_fiscal_years=st.session_state["live_fiscal_years"],
    live_distributions=st.session_state["live_distributions"],
    live_departments=st.session_state["live_departments"],
    live_designations=st.session_state["live_designations"],
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
            res, opener = verify_erpnext_credentials(
                usr,
                pwd,
                client_failed_attempts=component_val.get("failed_attempts", 0)
            )
            st.session_state["auth_response"] = res
            st.session_state["pending_auth_delivery"] = True
            if res.get("authorized") and opener:
                st.session_state["opener"] = opener
                _get_shared_opener_store()["opener"] = opener
                _sync_live_masterlists(opener)
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
            st.session_state["pending_reset_delivery"] = True
            st.rerun()
        elif action == "logout":
            token = st.session_state.get("session_token") or get_query_param("sfe_session")
            if token and token in ACTIVE_SESSIONS:
                ACTIVE_SESSIONS.pop(token, None)
            clear_query_param("sfe_session")
            st.session_state["auth_response"] = None
            st.session_state["pending_auth_delivery"] = False
            st.session_state["reset_password_response"] = None
            st.session_state["pending_reset_delivery"] = False
            st.session_state["opener"] = None
            _get_shared_opener_store()["opener"] = None
            st.session_state["live_territories"] = None
            st.session_state["live_sales_persons"] = None
            st.session_state["live_employees"] = None
            st.session_state["live_users"] = None
            st.session_state["live_institutions"] = None
            st.session_state["live_hcp_accounts"] = None
            st.session_state["live_item_groups"] = None
            st.session_state["live_fiscal_years"] = None
            st.session_state["live_distributions"] = None
            st.session_state["live_departments"] = None
            st.session_state["live_designations"] = None
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
        elif action in [
            "tree_add", "bulk_tree_add", "tree_edit", "bulk_tree_edit",
            "tree_rename", "bulk_tree_rename", "tree_delete",
            "territory_toggle_status", "territory_deactivate",
            "bulk_decommission", "bulk_archive", "resignation_handover",
            "tree_refresh", "sales_person_create", "employee_create", "doctor_transfer"
        ]:
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
                _sync_live_masterlists(opener, core_only=(action == "tree_refresh" and bool(component_val.get("silent"))))

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

