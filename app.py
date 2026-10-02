import streamlit as st
import streamlit.components.v1 as components
import os
import json
import urllib.request
import urllib.parse
import ssl
import http.cookiejar

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
    .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
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
    }
</style>
""", unsafe_allow_html=True)

ERPNEXT_SERVER_URL = os.environ.get("ERPNEXT_URL", "https://dev.pmii-marketing.com")

def verify_erpnext_credentials(usr, pwd):
    if not usr or not pwd:
        return {
            "success": False,
            "authorized": False,
            "message": "Both username and password are required."
        }

    usr = usr.strip()
    pwd = pwd.strip()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=ctx)
    )

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
        login_res = opener.open(login_req, timeout=5)
        login_data = json.loads(login_res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {
                "success": False,
                "authorized": False,
                "message": "Invalid username or password. Please verify your credentials registered in https://dev.pmii-marketing.com/app/user."
            }
        return {
            "success": False,
            "authorized": False,
            "message": f"ERPNext authentication error (HTTP {e.code}). Please try again."
        }
    except Exception as e:
        return {
            "success": False,
            "authorized": False,
            "message": f"Cannot connect to ERPNext ({str(e)}). Please verify your network."
        }

    if login_data.get("message") != "Logged In":
        return {
            "success": False,
            "authorized": False,
            "message": "Authentication failed on ERPNext."
        }

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
        }

    roles = []
    role_profile = ""

    try:
        quoted_usr = urllib.parse.quote(usr)
        user_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/resource/User/{quoted_usr}",
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        user_res = opener.open(user_req, timeout=5)
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
        }

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
    }

# 3. Mount Territory Reconfiguration Portal Component
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(CURRENT_DIR, "index.html")
PORTAL_HTML = os.path.join(CURRENT_DIR, "territory_reconfiguration_portal.html")

# Ensure index.html exists for Streamlit component resolution
if not os.path.exists(INDEX_HTML) and os.path.exists(PORTAL_HTML):
    import shutil
    shutil.copy2(PORTAL_HTML, INDEX_HTML)

portal_component = components.declare_component("pims_portal", path=CURRENT_DIR)

if "auth_response" not in st.session_state:
    st.session_state["auth_response"] = None
if "last_auth_timestamp" not in st.session_state:
    st.session_state["last_auth_timestamp"] = 0

# Render the web app component directly (Opens directly to the native login view - Image 2)
component_val = portal_component(
    auth_response=st.session_state["auth_response"],
    key="pims_portal_app"
)

# Handle authentication events dispatched from the portal
if component_val and isinstance(component_val, dict):
    action = component_val.get("action")
    ts = component_val.get("timestamp", 0)

    # De-duplicate events to strictly eliminate infinite rerun loops
    if ts > st.session_state["last_auth_timestamp"]:
        st.session_state["last_auth_timestamp"] = ts
        if action == "login":
            usr = component_val.get("usr")
            pwd = component_val.get("pwd")
            res = verify_erpnext_credentials(usr, pwd)
            st.session_state["auth_response"] = res
            st.rerun()
        elif action == "logout":
            st.session_state["auth_response"] = None
            st.rerun()
