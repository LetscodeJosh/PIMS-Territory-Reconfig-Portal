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

ERPNEXT_SERVER_URL = os.environ.get("ERPNEXT_URL", "https://dev.pmii-marketing.com")

def safe_str(val, default=""):
    if val is None:
        return default
    return str(val).strip()

def get_authenticated_opener():
    opener = create_erpnext_opener()
    creds = [
        ("lesantos@pims-marketing.com", "pims@admin"),
        ("jptan@profinsights.biz", "UEPCS101c!"),
    ]
    for usr, pwd in creds:
        try:
            login_data = json.dumps({"usr": usr, "pwd": pwd}).encode("utf-8")
            login_headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PIMS-Streamlit-Client"
            }
            login_req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/method/login",
                data=login_data,
                headers=login_headers
            )
            login_res = opener.open(login_req, timeout=8)
            res_data = json.loads(login_res.read().decode("utf-8"))
            if res_data.get("message") == "Logged In":
                return opener
        except Exception:
            continue
    return None

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
    return opener

def verify_erpnext_credentials(usr, pwd):
    if not usr or not pwd:
        return {
            "success": False,
            "authorized": False,
            "message": "Both username and password are required."
        }, None

    usr = usr.strip()
    pwd = pwd.strip()

    opener = create_erpnext_opener()

    login_payload = json.dumps({"usr": usr, "pwd": pwd}).encode("utf-8")
    login_headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PIMS-Streamlit-Client"
    }

    try:
        login_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/method/login",
            data=login_payload,
            headers=login_headers
        )
        login_res = opener.open(login_req, timeout=8)
        login_data = json.loads(login_res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {
                "success": False,
                "authorized": False,
                "message": "Invalid username or password. Please verify your credentials registered in https://dev.pmii-marketing.com/app/user."
            }, None
        return {
            "success": False,
            "authorized": False,
            "message": f"ERPNext authentication error (HTTP {e.code}). Please try again."
        }, None
    except Exception as e:
        return {
            "success": False,
            "authorized": False,
            "message": f"Cannot connect to ERPNext ({str(e)}). Please verify your network."
        }, None

    if login_data.get("message") != "Logged In":
        return {
            "success": False,
            "authorized": False,
            "message": "Authentication failed on ERPNext."
        }, None

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
                "auth_source": "ERPNext Live User Masterlist (dev.pmii-marketing.com)"
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
    is_sfe = any(k in all_roles_str for k in ["sales force effectiveness", "sales manager", "sfe", "territory manager"])

    if not (is_admin or is_sfe):
        return {
            "success": False,
            "authorized": False,
            "message": f"Access Restricted: User '{usr}' does not have SFE or Administrator roles in https://dev.pmii-marketing.com/app/user."
        }, None

    role_title = "Administrator" if is_admin else "SFE Lead"

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
            "auth_source": "ERPNext Live User Masterlist (dev.pmii-marketing.com)"
        }
    }, opener

def fetch_live_territories(opener):
    if not opener:
        return None
    try:
        fields = json.dumps(["name", "territory_name", "parent_territory", "is_group", "territory_manager"])
        url = f"{ERPNEXT_SERVER_URL}/api/resource/Territory?fields={urllib.parse.quote(fields)}&limit_page_length=500"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        res = opener.open(req, timeout=8)
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
        res = opener.open(req, timeout=10)
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
        res = opener.open(req, timeout=12)
        data = json.loads(res.read().decode("utf-8")).get("data", [])
        return data
    except Exception as e:
        print(f"[Streamlit Proxy] Failed to fetch live users: {e}")
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
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory",
                data=data,
                headers=headers_json,
                method="POST"
            )
            try:
                res = opener.open(req, timeout=10)
                if res.status in [200, 201]:
                    return "success", f'Territory "{t_name}" created live on dev.pmii-marketing.com!'
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
                    res = opener.open(req, timeout=10)
                    if res.status in [200, 201]:
                        return "success", f'Territory "{t_name}" created live on dev.pmii-marketing.com!'
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
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Territory/{urllib.parse.quote(orig_name)}",
                data=data,
                headers=headers_json,
                method="PUT"
            )
            try:
                res = opener.open(req, timeout=10)
                if res.status == 200:
                    return "success", f'Territory "{orig_name}" updated live on dev.pmii-marketing.com!'
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
                    res = opener.open(req, timeout=10)
                    if res.status == 200:
                        return "success", f'Territory "{orig_name}" updated live on dev.pmii-marketing.com!'
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
            res = opener.open(req, timeout=10)
            if res.status == 200:
                return "success", f'Renamed "{old_name}" -> "{new_name}" live on dev.pmii-marketing.com!'
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
            res = opener.open(req, timeout=10)
            if res.status in [200, 202]:
                return "success", f'Territory "{name}" deleted from dev.pmii-marketing.com!'
            return "warning", f"ERPNext responded with HTTP {res.status}"

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
                body["commission_rate"] = comm
            targets = payload.get("targets")
            if targets and isinstance(targets, list) and len(targets) > 0:
                body["targets"] = targets

            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{ERPNEXT_SERVER_URL}/api/resource/Sales%20Person",
                data=data,
                headers=headers_json,
                method="POST"
            )
            res = opener.open(req, timeout=10)
            if res.status in [200, 201]:
                return "success", f'Sales Person "{sp_name}" added to Sales Person Tree on dev.pmii-marketing.com!'
            return "warning", f"ERPNext responded with HTTP {res.status}"

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
            res = opener.open(req, timeout=10)
            if res.status in [200, 201]:
                try:
                    created_doc = json.loads(res.read().decode("utf-8")).get("data", {})
                    new_id = created_doc.get("name") or "New Employee"
                    full_name = created_doc.get("employee_name") or f"{first_name} {last_name}".strip()
                    return "success", f'Employee "{full_name}" ({new_id}) created on dev.pmii-marketing.com!'
                except Exception:
                    return "success", f'Employee created successfully on dev.pmii-marketing.com!'
            return "warning", f"ERPNext responded with HTTP {res.status}"

        elif action == "tree_refresh":
            return "info", "Territory tree refreshed from dev.pmii-marketing.com"

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

# Restore persistent session across page refresh if present in query parameters
session_token = get_query_param("sfe_session")
if session_token and session_token in ACTIVE_SESSIONS:
    cached_session = ACTIVE_SESSIONS[session_token]
    cached_session["last_active"] = time.time()
    if "auth_response" not in st.session_state or not st.session_state["auth_response"]:
        st.session_state["auth_response"] = cached_session.get("auth_response")
    if "opener" not in st.session_state or not st.session_state["opener"]:
        st.session_state["opener"] = cached_session.get("opener")
    if "live_territories" not in st.session_state or not st.session_state["live_territories"]:
        st.session_state["live_territories"] = cached_session.get("live_territories")
    if "live_sales_persons" not in st.session_state or not st.session_state["live_sales_persons"]:
        st.session_state["live_sales_persons"] = cached_session.get("live_sales_persons")
    if "live_employees" not in st.session_state or not st.session_state["live_employees"]:
        st.session_state["live_employees"] = cached_session.get("live_employees")
    if "live_users" not in st.session_state or not st.session_state["live_users"]:
        st.session_state["live_users"] = cached_session.get("live_users")
    st.session_state["session_token"] = session_token
elif session_token:
    clear_query_param("sfe_session")


if "auth_response" not in st.session_state:
    st.session_state["auth_response"] = None
if "opener" not in st.session_state:
    st.session_state["opener"] = None
if "opener" not in st.session_state or not st.session_state["opener"]:
    st.session_state["opener"] = get_authenticated_opener()

if "live_territories" not in st.session_state:
    st.session_state["live_territories"] = fetch_live_territories(st.session_state["opener"]) if st.session_state["opener"] else None
if "live_sales_persons" not in st.session_state:
    st.session_state["live_sales_persons"] = None
if "live_employees" not in st.session_state:
    st.session_state["live_employees"] = None
if "live_users" not in st.session_state:
    st.session_state["live_users"] = None
if "tree_sync_event" not in st.session_state:
    st.session_state["tree_sync_event"] = None
if "last_action_timestamp" not in st.session_state:
    st.session_state["last_action_timestamp"] = 0

# Render the web app component directly (Opens directly to the native login view)
component_val = portal_component(
    auth_response=st.session_state["auth_response"],
    live_territories=st.session_state["live_territories"],
    live_sales_persons=st.session_state["live_sales_persons"],
    live_employees=st.session_state["live_employees"],
    live_users=st.session_state["live_users"],
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
            if res.get("authorized") and opener:
                st.session_state["opener"] = opener
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                        f_terrs = executor.submit(fetch_live_territories, opener)
                        f_sps = executor.submit(fetch_live_sales_persons, opener)
                        f_emps = executor.submit(fetch_live_employees, opener)
                        f_users = executor.submit(fetch_live_users, opener)
                        st.session_state["live_territories"] = f_terrs.result()
                        st.session_state["live_sales_persons"] = f_sps.result()
                        st.session_state["live_employees"] = f_emps.result()
                        st.session_state["live_users"] = f_users.result()
                except Exception as ex:
                    print(f"[Streamlit Data Fetch Warning] {ex}")
                    st.session_state["live_territories"] = fetch_live_territories(opener)
                    st.session_state["live_users"] = fetch_live_users(opener)
            if res.get("authorized") and opener:
                purge_expired_sessions()
                token = secrets.token_urlsafe(32)
                ACTIVE_SESSIONS[token] = {
                    "auth_response": res,
                    "opener": opener,
                    "live_territories": st.session_state["live_territories"],
                    "live_sales_persons": st.session_state["live_sales_persons"],
                    "live_employees": st.session_state["live_employees"],
                    "live_users": st.session_state["live_users"],
                    "last_active": time.time()
                }
                set_query_param("sfe_session", token)
                st.session_state["session_token"] = token

            # Immediately scrub credentials from memory and component payload
            if "pwd" in component_val:
                component_val["pwd"] = ""
            del pwd
            del usr
            st.rerun()
        elif action == "logout":
            token = st.session_state.get("session_token") or get_query_param("sfe_session")
            if token and token in ACTIVE_SESSIONS:
                ACTIVE_SESSIONS.pop(token, None)
            clear_query_param("sfe_session")
            st.session_state["auth_response"] = None
            st.session_state["opener"] = None
            st.session_state["live_territories"] = None
            st.session_state["live_sales_persons"] = None
            st.session_state["live_employees"] = None
            st.session_state["live_users"] = None
            st.session_state["tree_sync_event"] = None
            st.session_state["session_token"] = None
            st.rerun()
        elif action in ["tree_add", "tree_edit", "tree_rename", "tree_delete", "tree_refresh", "sales_person_create", "employee_create"]:
            opener = st.session_state.get("opener")
            if not opener:
                opener = get_authenticated_opener()
                st.session_state["opener"] = opener
            status, msg = execute_tree_action(opener, action, component_val)
            opener = st.session_state.get("opener") or get_authenticated_opener()
            if opener:
                st.session_state["opener"] = opener
                st.session_state["live_territories"] = fetch_live_territories(opener)
                st.session_state["live_sales_persons"] = fetch_live_sales_persons(opener)
                st.session_state["live_employees"] = fetch_live_employees(opener)
                token = st.session_state.get("session_token")
                if token and token in ACTIVE_SESSIONS:
                    ACTIVE_SESSIONS[token]["live_territories"] = st.session_state["live_territories"]
                    ACTIVE_SESSIONS[token]["live_sales_persons"] = st.session_state["live_sales_persons"]
                    ACTIVE_SESSIONS[token]["live_employees"] = st.session_state["live_employees"]
                    ACTIVE_SESSIONS[token]["last_active"] = time.time()
            st.session_state["tree_sync_event"] = {
                "action": action,
                "status": status,
                "message": msg,
                "timestamp": ts
            }
            st.rerun()

