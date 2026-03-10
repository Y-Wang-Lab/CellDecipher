"""Pipeline Assistant - Chat interface for pipeline Q&A and run monitoring."""

import streamlit as st
import os
import sys

# Import services
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, app_dir)

from config.settings import settings
from services.tower_service import TowerService
from services.multifish_service import MultifishService


def get_tower_service():
    """Get or create Tower service using the user's session token and workspace."""
    token = st.session_state.get("tower_token", "")
    workspace = st.session_state.get("tower_workspace", "")
    if not token:
        return None

    # Cache the service per token+workspace so we recreate on changes
    cache_key = "tower_service_obj"
    cache_tag = f"{token}:{workspace}"
    cached = st.session_state.get(cache_key)
    if cached and getattr(cached, "_cache_tag", None) == cache_tag:
        return cached

    svc = TowerService(
        api_endpoint=settings.tower_api_endpoint,
        access_token=token,
        workspace=workspace or None,
    )
    svc._cache_tag = cache_tag
    st.session_state[cache_key] = svc
    return svc


@st.cache_resource
def get_multifish_service():
    """Initialize the multifish assistant service (cached across reruns).

    Note: tower_service is set to None here and injected per-session
    via svc.tower_service before each chat call.
    """
    api_key = (
        settings.openai_api_key
        if settings.llm_provider == "openai"
        else settings.anthropic_api_key
    )

    # Resolve GitHub token: Streamlit secrets > settings > env var
    github_token = ""
    try:
        github_token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        pass
    if not github_token:
        github_token = settings.github_token or os.environ.get("GITHUB_TOKEN", "")

    return MultifishService(
        knowledge_dir=settings.multifish_knowledge_dir,
        tower_service=None,
        llm_provider=settings.llm_provider,
        api_key=api_key,
        llm_model=settings.llm_model,
        github_token=github_token,
        github_repo=settings.github_repo,
        github_knowledge_path=settings.github_knowledge_path,
        knowledge_branch=settings.multifish_knowledge_branch,
    )


# Page header
st.title("Pipeline Assistant")
st.caption("Ask about pipeline parameters, troubleshoot errors, or check your Seqera runs.")

# Initialize session state
if "assistant_messages" not in st.session_state:
    st.session_state.assistant_messages = []
if "tower_token" not in st.session_state:
    st.session_state.tower_token = ""
if "tower_workspace" not in st.session_state:
    st.session_state.tower_workspace = ""
if "tower_connected" not in st.session_state:
    st.session_state.tower_connected = None

svc = get_multifish_service()

# Always inject the user's Tower service (session-scoped) into the cached service
svc.tower_service = get_tower_service()

# Sidebar
with st.sidebar:
    st.markdown("---")
    st.markdown("**Seqera Platform**")

    token_input = st.text_input(
        "Access token",
        value=st.session_state.tower_token,
        type="password",
        placeholder="Paste your Seqera access token",
        help="Get your token from cloud.seqera.io → Your tokens",
    )

    workspace_input = st.text_input(
        "Workspace",
        value=st.session_state.tower_workspace,
        placeholder="Wang_Lab/multifish",
        help="Format: org_name/workspace_name (from your Seqera URL)",
    )

    # Detect changes
    if token_input != st.session_state.tower_token or workspace_input != st.session_state.tower_workspace:
        st.session_state.tower_token = token_input
        st.session_state.tower_workspace = workspace_input
        st.session_state.tower_connected = None  # reset status

    if st.session_state.tower_token:
        if st.button("Test connection"):
            tower = get_tower_service()
            if tower and tower.test_connection():
                st.session_state.tower_connected = True
                # Verify workspace access by listing workflows
                workflows = tower.list_workflows(limit=1)
                if workflows:
                    st.session_state.tower_connected = True
                elif st.session_state.tower_workspace:
                    st.session_state.tower_connected = "no_workspace"
            else:
                st.session_state.tower_connected = False
            st.rerun()

        if st.session_state.tower_connected is True:
            st.success("Connected")
        elif st.session_state.tower_connected == "no_workspace":
            st.warning("Token works but no runs found — check workspace name")
        elif st.session_state.tower_connected is False:
            st.error("Connection failed — check your token")
    else:
        st.caption("Enter your token to enable run monitoring")

    # Clear chat button
    st.markdown("---")
    if st.button("Clear conversation"):
        st.session_state.assistant_messages = []
        st.rerun()

# Display conversation history
for msg in st.session_state.assistant_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if user_input := st.chat_input("Ask about the EASI-FISH pipeline..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(user_input)

    # Add to history
    st.session_state.assistant_messages.append({"role": "user", "content": user_input})

    # Get assistant response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            history = st.session_state.assistant_messages[:-1]
            response = svc.chat(user_input, history)

        st.markdown(response)

    # Save assistant response
    st.session_state.assistant_messages.append({"role": "assistant", "content": response})
