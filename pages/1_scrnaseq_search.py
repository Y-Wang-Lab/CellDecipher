"""scRNA-seq Search Page - Search and download single-cell data."""

import streamlit as st
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm_service import LLMService, ParsedQuery
from services.cellxgene_service import CellxGeneService
from components.progress_indicators import StepProgress

# Page config
st.title("🔍 scRNA-seq Data Search")
st.markdown("Search public single-cell RNA-seq databases using natural language")

# Initialize services
@st.cache_resource
def get_llm_service():
    return LLMService()

@st.cache_resource
def get_cellxgene_service():
    return CellxGeneService()

# Initialize session state
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "parsed_query" not in st.session_state:
    st.session_state.parsed_query = None
if "fetched_adata" not in st.session_state:
    st.session_state.fetched_adata = None

# Search section
st.subheader("1. Search")

# Search mode tabs
search_mode = st.radio(
    "Search mode",
    ["Natural Language", "Advanced Filters", "Upload Data"],
    horizontal=True
)

llm_service = get_llm_service()
cellxgene_service = get_cellxgene_service()

if search_mode == "Natural Language":
    st.markdown("Describe the data you're looking for:")
    query = st.text_area(
        "Search query",
        height=100,
        placeholder="Example: T cells from lung cancer patients\nExample: Mouse brain neurons from adult males",
        label_visibility="collapsed"
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🔍 Search", type="primary"):
            if query.strip():
                with st.spinner("Parsing query..."):
                    parsed = llm_service.parse_query(query)
                    st.session_state.parsed_query = parsed

                # Show parsed parameters
                st.info(f"""
                **Parsed Query:**
                - Organism: {parsed.organism}
                - Tissue: {parsed.tissue or 'Any'}
                - Cell Type: {parsed.cell_type or 'Any'}
                - Disease: {parsed.disease or 'Any'}
                """)

                with st.spinner("Searching CELLxGENE Census..."):
                    results = cellxgene_service.search_datasets(
                        organism=parsed.organism,
                        tissue=parsed.tissue,
                        cell_type=parsed.cell_type,
                        disease=parsed.disease,
                    )
                    st.session_state.search_results = results

                st.success(f"Found {len(results)} datasets")
            else:
                st.warning("Please enter a search query")

elif search_mode == "Advanced Filters":
    col1, col2 = st.columns(2)

    with col1:
        organism = st.selectbox("Organism", ["Homo sapiens", "Mus musculus"])

        # Get available tissues dynamically
        tissues = st.multiselect(
            "Tissue",
            ["lung", "heart", "brain", "liver", "kidney", "blood", "skin", "bone marrow"],
            help="Select one or more tissues"
        )

    with col2:
        cell_types = st.multiselect(
            "Cell Type",
            ["T cell", "B cell", "macrophage", "neuron", "fibroblast", "epithelial cell"],
            help="Select one or more cell types"
        )

        diseases = st.multiselect(
            "Disease/Condition",
            ["normal", "cancer", "COVID-19", "diabetes", "Alzheimer disease"],
            help="Select disease states"
        )

    if st.button("🔍 Search", type="primary"):
        with st.spinner("Searching..."):
            results = cellxgene_service.search_datasets(
                organism=organism,
                tissue=tissues if tissues else None,
                cell_type=cell_types if cell_types else None,
                disease=diseases if diseases else None,
            )
            st.session_state.search_results = results
        st.success(f"Found {len(results)} datasets")

else:  # Upload Data
    st.markdown("Upload your own H5AD file to analyze:")
    uploaded_file = st.file_uploader(
        "Upload H5AD file",
        type=["h5ad"],
        help="Upload an AnnData H5AD file"
    )

    if uploaded_file:
        import tempfile
        import anndata as ad

        with tempfile.NamedTemporaryFile(delete=False, suffix='.h5ad') as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            adata = ad.read_h5ad(tmp_path)
            st.session_state.fetched_adata = adata
            st.success(f"Loaded: {adata.n_obs} cells × {adata.n_vars} genes")

            # Show basic info
            st.markdown("**Dataset Summary:**")
            col1, col2, col3 = st.columns(3)
            col1.metric("Cells", f"{adata.n_obs:,}")
            col2.metric("Genes", f"{adata.n_vars:,}")
            col3.metric("Obs Columns", len(adata.obs.columns))

            if len(adata.obs.columns) > 0:
                with st.expander("View Metadata"):
                    st.dataframe(adata.obs.head(20))

        except Exception as e:
            st.error(f"Error loading file: {e}")
        finally:
            os.unlink(tmp_path)

# Display search results
if st.session_state.search_results:
    st.divider()
    st.subheader("2. Results")

    results = st.session_state.search_results

    # Results table
    results_df = pd.DataFrame([{
        "Dataset ID": r.dataset_id,
        "Tissue": r.tissue,
        "Cells": f"{r.cell_count:,}",
        "Assay": r.assay,
    } for r in results])

    st.dataframe(results_df, use_container_width=True, hide_index=True)

    # Dataset selection
    st.divider()
    st.subheader("3. Fetch Data")

    selected_idx = st.selectbox(
        "Select a dataset to download",
        range(len(results)),
        format_func=lambda x: f"{results[x].dataset_id} ({results[x].cell_count:,} cells)"
    )

    selected = results[selected_idx]

    col1, col2 = st.columns(2)
    with col1:
        max_cells = st.slider("Max cells to download", 1000, 50000, 10000)

    with col2:
        st.markdown(f"""
        **Selected Dataset:**
        - ID: {selected.dataset_id}
        - Tissue: {selected.tissue}
        - Cells: {selected.cell_count:,}
        """)

    if st.button("📥 Fetch Dataset", type="primary"):
        with st.spinner(f"Fetching data (max {max_cells} cells)..."):
            # Build filter based on selection
            filter_parts = [f"dataset_id == '{selected.dataset_id}'"]
            filter_str = " and ".join(filter_parts)

            adata = cellxgene_service.fetch_data(
                organism=st.session_state.parsed_query.organism if st.session_state.parsed_query else "Homo sapiens",
                obs_filter=filter_str,
                max_cells=max_cells,
            )

            if adata is not None:
                st.session_state.fetched_adata = adata
                st.success(f"Downloaded: {adata.n_obs} cells × {adata.n_vars} genes")
            else:
                st.error("Failed to fetch data")

# Display fetched data
if st.session_state.fetched_adata is not None:
    st.divider()
    st.subheader("4. Preview & Analyze")

    adata = st.session_state.fetched_adata

    col1, col2, col3 = st.columns(3)
    col1.metric("Cells", f"{adata.n_obs:,}")
    col2.metric("Genes", f"{adata.n_vars:,}")
    col3.metric("Memory", f"{adata.X.nbytes / 1e6:.1f} MB")

    # Preview tabs
    tabs = st.tabs(["Cell Metadata", "Gene Info", "Expression Preview"])

    with tabs[0]:
        st.dataframe(adata.obs.head(50), use_container_width=True)

    with tabs[1]:
        st.dataframe(adata.var.head(50), use_container_width=True)

    with tabs[2]:
        import numpy as np
        if hasattr(adata.X, "toarray"):
            preview = adata.X[:10, :10].toarray()
        else:
            preview = adata.X[:10, :10]
        st.write("Expression matrix (first 10 cells × 10 genes):")
        st.dataframe(pd.DataFrame(
            preview,
            index=adata.obs_names[:10],
            columns=adata.var_names[:10]
        ))

    # Actions
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Analyze in Expression Analysis", type="primary"):
            # Store in session state for Expression Analysis page
            st.session_state.adata = adata
            st.switch_page("pages/4_expression_analysis.py")

    with col2:
        # Download button
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.h5ad') as tmp:
            adata.write_h5ad(tmp.name)
            with open(tmp.name, 'rb') as f:
                st.download_button(
                    "📥 Download H5AD",
                    f.read(),
                    file_name="scrnaseq_data.h5ad",
                    mime="application/octet-stream"
                )
            os.unlink(tmp.name)

# Help section
with st.expander("ℹ️ About Data Sources"):
    st.markdown("""
    **CELLxGENE Census** is a curated collection of single-cell RNA-seq datasets from the
    Chan Zuckerberg Initiative. It includes:

    - Millions of cells from hundreds of studies
    - Standardized cell type annotations
    - Human and mouse data
    - Various tissues and diseases

    The natural language search uses AI to interpret your query and convert it to
    structured search parameters.

    **Tips:**
    - Be specific about tissue, cell type, and disease
    - Mention species if searching for mouse data
    - Large datasets may take time to download
    """)
