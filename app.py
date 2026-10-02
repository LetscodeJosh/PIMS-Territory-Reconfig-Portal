import streamlit as st
import streamlit.components.v1 as components
import os

# 1. Enterprise Streamlit Page Configuration
st.set_page_config(
    page_title="PIMS • Territory Reconfiguration Portal",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Modern Clean Full-Screen CSS (Hides Streamlit Chrome & Maximizes Workspace)
st.markdown("""
<style>
    /* Remove padding & maximize viewport */
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
        max-width: 100% !important;
    }
    /* Hide Streamlit header, hamburger menu and footer */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    footer {
        display: none !important;
    }
    /* Clean background container */
    iframe {
        border: none !important;
        width: 100% !important;
    }
</style>
""", unsafe_allow_html=True)

# 3. Path to Self-Contained Web Portal
HTML_FILE = os.path.join(os.path.dirname(__file__), "territory_reconfiguration_portal.html")

if os.path.exists(HTML_FILE):
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        portal_html = f.read()

    # 4. Render Portal Fullscreen (100% responsive with smooth internal scrolling)
    components.html(portal_html, height=1050, scrolling=True)
else:
    st.error("⚠️ Portal HTML file not found! Please make sure 'territory_reconfiguration_portal.html' is in the same directory as app.py.")
