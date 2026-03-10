"""Session state management for Streamlit."""

import streamlit as st
from typing import Optional, Any, List, Dict
import anndata as ad


class SessionManager:
    """Manages session state for the application."""

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get a value from session state."""
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value: Any) -> None:
        """Set a value in session state."""
        st.session_state[key] = value

    @staticmethod
    def get_adata(key: str = "current_adata") -> Optional[ad.AnnData]:
        """Get AnnData object from session state."""
        return st.session_state.get(key)

    @staticmethod
    def set_adata(adata: ad.AnnData, key: str = "current_adata") -> None:
        """Store AnnData object in session state."""
        st.session_state[key] = adata

    @staticmethod
    def get_analysis_history() -> List[Dict]:
        """Get analysis history from session state."""
        if "analysis_history" not in st.session_state:
            st.session_state.analysis_history = []
        return st.session_state.analysis_history

    @staticmethod
    def add_to_history(step: str, params: Dict) -> None:
        """Add analysis step to history."""
        history = SessionManager.get_analysis_history()
        history.append({"step": step, "params": params})
        st.session_state.analysis_history = history

    @staticmethod
    def clear_session() -> None:
        """Clear all session state."""
        for key in list(st.session_state.keys()):
            del st.session_state[key]

    @staticmethod
    def get_probe_results() -> Optional[Dict]:
        """Get probe design results from session state."""
        return st.session_state.get("probe_results")

    @staticmethod
    def set_probe_results(results: Dict) -> None:
        """Store probe design results in session state."""
        st.session_state["probe_results"] = results

    @staticmethod
    def get_gene_channel_mapping() -> Dict[str, str]:
        """Get gene to channel mapping from session state."""
        if "gene_channel_mapping" not in st.session_state:
            st.session_state.gene_channel_mapping = {}
        return st.session_state.gene_channel_mapping

    @staticmethod
    def set_gene_channel_mapping(mapping: Dict[str, str]) -> None:
        """Store gene to channel mapping in session state."""
        st.session_state["gene_channel_mapping"] = mapping
