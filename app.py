"""
CellDecipher - Main Application Entry Point

An all-in-one tool for EASI-FISH based spatial omics projects.
"""

import hashlib

import streamlit as st
from pathlib import Path

from config.settings import settings

# Page configuration
st.set_page_config(
    page_title="CellDecipher",
    page_icon="🧫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load custom CSS
def load_css():
    css_file = Path(__file__).parent / "assets" / "styles.css"
    if css_file.exists():
        with open(css_file) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Apply light theme CSS
def apply_theme():
    st.markdown("""
    <style>
    :root {
        --bg-primary: #f8fafc;
        --bg-secondary: #f1f5f9;
        --bg-tertiary: #e2e8f0;
        --bg-card: #ffffff;
        --bg-card-hover: #f8fafc;
        --accent-cyan: #0891b2;
        --accent-magenta: #db2777;
        --accent-green: #16a34a;
        --accent-amber: #d97706;
        --accent-purple: #7c3aed;
        --text-primary: #0f172a;
        --text-secondary: #475569;
        --text-muted: #94a3b8;
        --border-subtle: rgba(15, 23, 42, 0.1);
        --border-accent: rgba(8, 145, 178, 0.3);
        --gradient-card: linear-gradient(145deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 0.98) 100%);
        --shadow-glow-cyan: 0 0 20px rgba(8, 145, 178, 0.15);
        --shadow-glow-magenta: 0 0 20px rgba(219, 39, 119, 0.15);
        --shadow-card: 0 4px 24px rgba(0, 0, 0, 0.08);
        --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.12);
        --grid-opacity: 0.04;
    }
    </style>
    """, unsafe_allow_html=True)

def check_password():
    """Gate the app behind a password during testing."""
    if not settings.app_password_hash:
        return  # No password configured, allow access

    if st.session_state.get("authenticated"):
        return  # Already authenticated this session

    st.markdown("### CellDecipher Login")
    password = st.text_input("Password", type="password")
    if st.button("Enter"):
        entered_hash = hashlib.sha256(password.encode()).hexdigest()
        if entered_hash == settings.app_password_hash:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

check_password()
load_css()
apply_theme()

# Define pages
home_page = st.Page("pages/home.py", title="CellDecipher", url_path="", default=True)
pages = {
    "": [home_page],
    "Tools": [
        st.Page("pages/1_scrnaseq_search.py", title="scRNA-seq Search", url_path="scrnaseq-search"),
        st.Page("pages/2_probe_design.py", title="Probe Design", url_path="probe-design"),
        st.Page("pages/3_pipeline_monitor.py", title="Pipeline Assistant", url_path="pipeline-assistant"),
        st.Page("pages/4_expression_analysis.py", title="Expression Analysis", url_path="expression-analysis"),
    ],
}

# Clickable CellDecipher header above the nav
with st.sidebar:
    st.page_link(home_page, label="🧫 CellDecipher")

pg = st.navigation(pages)

with st.sidebar:
    st.markdown("""
    <style>
    /* Style the CellDecipher page_link as a prominent header */
    section[data-testid="stSidebar"] [data-testid*="PageLink"]:first-of-type a {
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: var(--text-primary, #0f172a) !important;
        text-decoration: none !important;
    }
    section[data-testid="stSidebar"] [data-testid*="PageLink"]:first-of-type a:hover {
        color: var(--accent-cyan, #0891b2) !important;
    }

    /* Font size for Tools dropdown items */
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] ul ul a {
        font-size: 1.0rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Run selected page
pg.run()
