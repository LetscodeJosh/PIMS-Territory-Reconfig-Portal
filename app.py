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

# 2. Modern Clean Styling
st.markdown("""
<style>
    /* Remove padding & maximize viewport */
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
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
        width: 100% !important;
    }
    .auth-card {
        background: #18181B;
        border: 1px solid #27272A;
        border-radius: 12px;
        padding: 30px;
        color: #FFFFFF;
        max-width: 480px;
        margin: 40px auto;
        box-shadow: 0 16px 40px rgba(0,0,0,0.5);
    }
    .auth-title {
        font-size: 20px;
        font-weight: 800;
        color: #FFFFFF;
        margin-bottom: 6px;
    }
    .auth-subtitle {
        font-size: 13px;
        color: #A1A1AA;
        margin-bottom: 22px;
        line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)

ERPNEXT_SERVER_URL = "https://dev.pmii-marketing.com"

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
        login_res = opener.open(login_req, timeout=10)
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
    roles = []
    role_profile = ""

    try:
        quoted_usr = urllib.parse.quote(usr)
        user_req = urllib.request.Request(
            f"{ERPNEXT_SERVER_URL}/api/resource/User/{quoted_usr}",
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        user_res = opener.open(user_req, timeout=10)
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

# 3. Check Authentication State
if "authenticated_user" not in st.session_state:
    # Render Secure Login Form
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center; padding: 24px 0 10px 0;">
            <div style="font-size:38px; margin-bottom:8px;">🗺️</div>
            <h2 style="font-size:22px; font-weight:800; color:#0F172A; margin:0 0 4px 0;">PIMS • Territory Reconfiguration</h2>
            <div style="font-size:13px; color:#64748B;">SFE CRM Masterlist & Hierarchy Workbench</div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("erpnext_login_form"):
            st.markdown("##### 🔐 Sign In with ERPNext")
            st.caption("Credentials are authenticated live against https://dev.pmii-marketing.com/app/user (Restricted to SFE and Administrator accounts).")
            username = st.text_input("Username or Email", placeholder="e.g. jptan@profinsights.biz")
            password = st.text_input("Password", type="password", placeholder="Enter your ERPNext password")
            submit = st.form_submit_button("Sign In to Reconfiguration Portal", use_container_width=True, type="primary")

            if submit:
                with st.spinner("Authenticating against dev.pmii-marketing.com..."):
                    res = verify_erpnext_credentials(username, password)
                    if res["success"] and res["authorized"]:
                        st.session_state["authenticated_user"] = res["user"]
                        st.success(res["message"])
                        st.rerun()
                    else:
                        st.error(f"⚠️ {res['message']}")

        st.markdown("""
        <div style="text-align:center; font-size:12px; color:#94A3B8; margin-top:16px;">
            Protected by ERPNext v15 Live Role-Based Access Control (RBAC)<br>
            Authorized: <strong>Sales Force Effectiveness (SFE)</strong> &bull; <strong>System Manager / Administrator</strong>
        </div>
        """, unsafe_allow_html=True)

else:
    # Authenticated Session
    user = st.session_state["authenticated_user"]

    # Top Navigation Bar with User Info & Logout
    top_col1, top_col2 = st.columns([4, 1])
    with top_col1:
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:8px; padding:4px 0;">
            <span style="font-size:13px; color:#0F172A; font-weight:700;">🗺️ PIMS Reconfiguration Portal</span>
            <span style="color:#CBD5E1;">&bull;</span>
            <span style="font-size:12px; color:#64748B;">User: <strong style="color:#0066FF;">{user['email']}</strong> [{user['role_title']}]</span>
        </div>
        """, unsafe_allow_html=True)
    with top_col2:
        if st.button("🚪 Sign Out", use_container_width=True):
            del st.session_state["authenticated_user"]
            st.rerun()

    # Read and Render the Web Portal HTML
    HTML_FILE = os.path.join(os.path.dirname(__file__), "territory_reconfiguration_portal.html")
    if os.path.exists(HTML_FILE):
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            portal_html = f.read()

        # Inject Authenticated User Session into the HTML so it bypasses the internal login and directly opens Territory Tree!
        user_json = json.dumps(user)
        injected_script = f"""
        <script>
            (function() {{
                const userObj = {user_json};
                sessionStorage.removeItem('sfe_portal_logged_out');
                sessionStorage.setItem('sfe_portal_user', JSON.stringify(userObj));
                document.addEventListener('DOMContentLoaded', function() {{
                    if (typeof applyAuthenticatedUser === 'function') {{
                        applyAuthenticatedUser(userObj);
                    }}
                }});
            }})();
        </script>
        """
        portal_html = portal_html.replace("</head>", f"{injected_script}\n</head>")

        components.html(portal_html, height=1080, scrolling=True)
    else:
        st.error("⚠️ Portal HTML file not found!")
