"""Expression Analysis Page - Analyze gene expression with spatial and morphology data."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from umap import UMAP

# Try to import Leiden clustering (optional dependency)
try:
    import leidenalg
    import igraph as ig
    LEIDEN_AVAILABLE = True
except ImportError:
    LEIDEN_AVAILABLE = False

def sort_categories(values):
    """Sort categories numerically if possible, otherwise alphabetically."""
    unique_vals = list(set(values))

    # Check if all values can be converted to numbers
    def try_numeric(x):
        if x in [None, 'nan', 'None', '', 'NaN']:
            return None
        try:
            return float(x)
        except (ValueError, TypeError):
            return None

    numeric_vals = [try_numeric(v) for v in unique_vals]

    # If all values are numeric (or null-like), sort numerically
    if all(n is not None or str(v) in ['nan', 'None', '', 'NaN', None] for n, v in zip(numeric_vals, unique_vals)):
        # Sort with numeric key, putting None/nan at the end
        return sorted(unique_vals, key=lambda x: (try_numeric(x) is None, try_numeric(x) or 0))
    else:
        # Fall back to alphabetical sort
        return sorted(unique_vals, key=lambda x: str(x).lower())

# Page config
st.title("Expression Analysis")
st.markdown("Analyze gene expression data with spatial coordinates and morphology features")

# Initialize session state
if "expr_data" not in st.session_state:
    st.session_state.expr_data = None
if "metadata" not in st.session_state:
    st.session_state.metadata = None
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = None

# Helper function to load data files
def load_data_file(uploaded_file, index_col=0):
    """Load data from various file formats."""
    filename = uploaded_file.name.lower()

    if filename.endswith('.csv'):
        df = pd.read_csv(uploaded_file, index_col=index_col)
    elif filename.endswith('.tsv') or filename.endswith('.txt'):
        df = pd.read_csv(uploaded_file, index_col=index_col, sep='\t')
    elif filename.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(uploaded_file, index_col=index_col)
    else:
        # Try to auto-detect delimiter
        content = uploaded_file.read().decode('utf-8')
        uploaded_file.seek(0)
        if '\t' in content.split('\n')[0]:
            df = pd.read_csv(uploaded_file, index_col=index_col, sep='\t')
        else:
            df = pd.read_csv(uploaded_file, index_col=index_col)
    return df

# File upload section
st.subheader("1. Load Data")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Gene Expression Data**")
    expr_file = st.file_uploader(
        "Upload expression data",
        type=["xlsx", "xls", "csv", "txt", "tsv"],
        help="Rows = cells (first column = cell IDs), Columns = genes, Values = mRNA counts",
        key="expr_upload"
    )

with col2:
    st.markdown("**Cell Metadata (Optional)**")
    meta_file = st.file_uploader(
        "Upload metadata",
        type=["xlsx", "xls", "csv", "txt", "tsv"],
        help="Rows = cells (first column = cell IDs matching expression data), Columns = features (x, y, z, size, etc.)",
        key="meta_upload"
    )

# Load expression data
if expr_file:
    with st.spinner("Loading expression data..."):
        try:
            df = load_data_file(expr_file, index_col=0)
            # Ensure numeric data
            df = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            st.session_state.expr_data = df
            st.success(f"Expression data: {df.shape[0]} cells × {df.shape[1]} genes")

            with st.expander("Preview expression data", expanded=False):
                st.dataframe(df.head(10), use_container_width=True)
        except Exception as e:
            st.error(f"Error loading expression file: {e}")

# Load metadata
if meta_file:
    with st.spinner("Loading metadata..."):
        try:
            meta_df = load_data_file(meta_file, index_col=0)
            st.session_state.metadata = meta_df
            st.success(f"Metadata: {meta_df.shape[0]} cells × {meta_df.shape[1]} features")

            # Show available columns
            with st.expander("Preview metadata", expanded=False):
                st.dataframe(meta_df.head(10), use_container_width=True)
                st.markdown(f"**Available features:** {', '.join(meta_df.columns.tolist())}")
        except Exception as e:
            st.error(f"Error loading metadata file: {e}")

# Check cell ID matching if both files are loaded
if st.session_state.expr_data is not None and st.session_state.metadata is not None:
    expr_cells = set(st.session_state.expr_data.index)
    meta_cells = set(st.session_state.metadata.index)
    common_cells = expr_cells & meta_cells

    if len(common_cells) == 0:
        st.error("No matching cell IDs found between expression data and metadata. Please check that cell IDs match.")
    elif len(common_cells) < len(expr_cells):
        st.warning(f"Found {len(common_cells)} matching cells out of {len(expr_cells)} expression cells and {len(meta_cells)} metadata cells.")
    else:
        st.success(f"All {len(common_cells)} cells matched between expression and metadata.")

# Analysis section
if st.session_state.expr_data is not None:
    df = st.session_state.expr_data

    st.divider()
    st.subheader("2. Data Summary")

    # Calculate QC metrics
    genes_per_cell = (df > 0).sum(axis=1)
    counts_per_cell = df.sum(axis=1)
    cells_per_gene = (df > 0).sum(axis=0)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cells", f"{df.shape[0]:,}")
    col2.metric("Genes", f"{df.shape[1]:,}")
    col3.metric("Median genes/cell", f"{genes_per_cell.median():.0f}")
    col4.metric("Median counts/cell", f"{counts_per_cell.median():.0f}")

    # Show data distribution
    with st.expander("Data Distribution", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            **Genes per cell:** {genes_per_cell.min()} - {genes_per_cell.max()} (median: {genes_per_cell.median():.0f})

            **Counts per cell:** {counts_per_cell.min():.0f} - {counts_per_cell.max():.0f} (median: {counts_per_cell.median():.0f})
            """)
        with col2:
            st.markdown(f"""
            **Cells per gene:** {cells_per_gene.min()} - {cells_per_gene.max()} (median: {cells_per_gene.median():.0f})
            """)

    st.divider()
    st.subheader("3. Quality Control")

    with st.expander("QC Parameters", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Cell Filtering**")
            min_genes_per_cell = st.slider(
                "Min genes per cell",
                min_value=0,
                max_value=int(genes_per_cell.max()),
                value=max(0, int(genes_per_cell.quantile(0.01))),
                help=f"Your data: {genes_per_cell.min()} - {genes_per_cell.max()}"
            )
            max_genes_per_cell = st.slider(
                "Max genes per cell",
                min_value=1,
                max_value=int(genes_per_cell.max()) + 100,
                value=int(genes_per_cell.max()) + 1,
                help=f"Your data: {genes_per_cell.min()} - {genes_per_cell.max()}"
            )
            min_counts_per_cell = st.slider(
                "Min counts per cell",
                min_value=0,
                max_value=int(counts_per_cell.max()),
                value=max(0, int(counts_per_cell.quantile(0.01))),
                help=f"Your data: {counts_per_cell.min():.0f} - {counts_per_cell.max():.0f}"
            )

        with col2:
            st.markdown("**Gene Filtering**")
            min_cells_per_gene = st.slider(
                "Min cells per gene",
                min_value=0,
                max_value=int(cells_per_gene.max()),
                value=max(1, int(cells_per_gene.quantile(0.01))),
                help=f"Your data: {cells_per_gene.min()} - {cells_per_gene.max()}"
            )

        # Calculate how many cells/genes pass filters
        cells_pass = (
            (genes_per_cell >= min_genes_per_cell) &
            (genes_per_cell <= max_genes_per_cell) &
            (counts_per_cell >= min_counts_per_cell)
        )
        genes_pass = cells_per_gene >= min_cells_per_gene

        n_cells_pass = cells_pass.sum()
        n_genes_pass = genes_pass.sum()

        col1, col2 = st.columns(2)
        with col1:
            if n_cells_pass == 0:
                st.error(f"No cells pass filters!")
            elif n_cells_pass < df.shape[0] * 0.1:
                st.warning(f"{n_cells_pass:,} / {df.shape[0]:,} cells pass ({100*n_cells_pass/df.shape[0]:.1f}%)")
            else:
                st.success(f"{n_cells_pass:,} / {df.shape[0]:,} cells pass ({100*n_cells_pass/df.shape[0]:.1f}%)")

        with col2:
            if n_genes_pass == 0:
                st.error(f"No genes pass filters!")
            elif n_genes_pass < df.shape[1] * 0.1:
                st.warning(f"{n_genes_pass:,} / {df.shape[1]:,} genes pass ({100*n_genes_pass/df.shape[1]:.1f}%)")
            else:
                st.success(f"{n_genes_pass:,} / {df.shape[1]:,} genes pass ({100*n_genes_pass/df.shape[1]:.1f}%)")

    st.divider()
    st.subheader("4. Analysis Parameters")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Dimensionality Reduction**")
        n_pcs = st.slider("Number of PCs", 2, min(50, df.shape[1], df.shape[0]),
                          value=min(20, df.shape[1], df.shape[0]))
        n_neighbors = st.slider("UMAP neighbors", 5, 50, 15)
        min_dist = st.slider("UMAP min_dist", 0.0, 1.0, 0.1, 0.05)

    with col2:
        st.markdown("**Clustering**")
        cluster_methods = ["K-means"]
        if LEIDEN_AVAILABLE:
            cluster_methods.insert(0, "Leiden (recommended)")
        else:
            st.caption("Install `leidenalg` and `python-igraph` for Leiden clustering")

        cluster_method = st.selectbox("Clustering method", cluster_methods)

        if "K-means" in cluster_method:
            n_clusters = st.slider("Number of clusters (K)", 2, 30, 10)
        else:
            leiden_resolution = st.slider("Leiden resolution", 0.1, 2.0, 1.0, 0.1,
                                          help="Higher = more clusters")
            n_clusters = None

    with col3:
        st.markdown("**Other Settings**")
        random_state = st.number_input("Random seed", value=42, min_value=0)

    st.divider()

    # Run analysis
    if st.button("Run Analysis", type="primary", use_container_width=True):

        progress_bar = st.progress(0, text="Starting analysis...")

        try:
            # Apply QC filters
            progress_bar.progress(10, text="Applying QC filters...")

            # Filter cells
            cells_pass = (
                (genes_per_cell >= min_genes_per_cell) &
                (genes_per_cell <= max_genes_per_cell) &
                (counts_per_cell >= min_counts_per_cell)
            )
            df_filtered = df.loc[cells_pass]

            # Filter genes
            cells_per_gene_filtered = (df_filtered > 0).sum(axis=0)
            genes_pass = cells_per_gene_filtered >= min_cells_per_gene
            df_filtered = df_filtered.loc[:, genes_pass]

            if df_filtered.shape[0] == 0:
                st.error("No cells passed QC filters. Please adjust thresholds.")
                st.stop()
            if df_filtered.shape[1] == 0:
                st.error("No genes passed QC filters. Please adjust thresholds.")
                st.stop()

            st.info(f"After QC: {df_filtered.shape[0]} cells × {df_filtered.shape[1]} genes")

            # Get raw counts
            X = df_filtered.values.astype(float)

            # Check for problematic values in input
            if np.isnan(X).any():
                nan_count = np.isnan(X).sum()
                st.warning(f"Found {nan_count} NaN values in input data, replacing with 0")
                X = np.nan_to_num(X, nan=0.0)

            if np.isinf(X).any():
                inf_count = np.isinf(X).sum()
                st.warning(f"Found {inf_count} Inf values in input data, replacing with 0")
                X = np.nan_to_num(X, posinf=0.0, neginf=0.0)

            # Check for extreme values
            max_val = np.abs(X).max()
            if max_val > 1e10:
                st.warning(f"Found extreme values (max={max_val:.2e}), clipping to reasonable range")
                X = np.clip(X, 0, 1e10)

            # Step 1: Log transform (log1p to handle zeros)
            progress_bar.progress(20, text="Log transforming...")
            X_log = np.log1p(X)

            # Handle any NaN/Inf values after log transform
            X_log = np.nan_to_num(X_log, nan=0.0, posinf=0.0, neginf=0.0)

            # Step 2: Remove zero-variance genes before scaling
            gene_vars = np.var(X_log, axis=0)
            nonzero_var = gene_vars > 1e-10
            if not nonzero_var.all():
                n_removed = (~nonzero_var).sum()
                st.warning(f"Removed {n_removed} zero-variance genes before scaling")
                X_log = X_log[:, nonzero_var]
                # Update gene names
                gene_names_filtered = [g for g, keep in zip(df_filtered.columns.tolist(), nonzero_var) if keep]
            else:
                gene_names_filtered = df_filtered.columns.tolist()

            # Step 3: Scale (z-score normalization)
            progress_bar.progress(40, text="Scaling...")
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_log)

            # Handle any NaN/Inf values from scaling
            X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)

            # Clip extreme values to prevent overflow
            X_scaled = np.clip(X_scaled, -10, 10)

            # Step 4: PCA
            progress_bar.progress(60, text="Running PCA...")

            # Ensure n_pcs doesn't exceed data dimensions
            max_pcs = min(X_scaled.shape[0] - 1, X_scaled.shape[1])
            actual_n_pcs = min(n_pcs, max_pcs)
            if actual_n_pcs < n_pcs:
                st.warning(f"Reduced PCs from {n_pcs} to {actual_n_pcs} (limited by data size)")

            pca = PCA(n_components=actual_n_pcs, random_state=random_state)
            X_pca = pca.fit_transform(X_scaled)

            # Step 4: UMAP
            progress_bar.progress(80, text="Running UMAP...")
            umap_model = UMAP(
                n_components=2,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                random_state=random_state
            )
            X_umap = umap_model.fit_transform(X_pca)

            # Step 6: Clustering
            progress_bar.progress(90, text="Clustering cells...")

            if "Leiden" in cluster_method and LEIDEN_AVAILABLE:
                from sklearn.neighbors import kneighbors_graph
                knn_graph = kneighbors_graph(X_pca, n_neighbors=n_neighbors, mode='connectivity')
                sources, targets = knn_graph.nonzero()
                edges = list(zip(sources, targets))
                g = ig.Graph(edges=edges, directed=False)
                g.simplify()
                partition = leidenalg.find_partition(
                    g, leidenalg.RBConfigurationVertexPartition,
                    resolution_parameter=leiden_resolution, seed=random_state
                )
                clusters = np.array(partition.membership)
            else:
                kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
                clusters = kmeans.fit_predict(X_pca)

            n_clusters_found = len(np.unique(clusters))
            st.info(f"Found {n_clusters_found} clusters")

            # Prepare metadata for filtered cells if available
            metadata_filtered = None
            if st.session_state.metadata is not None:
                meta_df = st.session_state.metadata
                common_cells = [c for c in df_filtered.index if c in meta_df.index]
                if len(common_cells) > 0:
                    metadata_filtered = meta_df.loc[common_cells].copy()

            # Store results
            st.session_state.analysis_results = {
                "X_log": X_log,
                "X_scaled": X_scaled,
                "X_pca": X_pca,
                "X_umap": X_umap,
                "clusters": clusters,
                "pca_model": pca,
                "variance_explained": pca.explained_variance_ratio_,
                "cell_names": df_filtered.index.tolist(),
                "gene_names": gene_names_filtered,
                "metadata": metadata_filtered,
            }

            progress_bar.progress(100, text="Analysis complete!")
            st.success("Analysis complete!")

        except Exception as e:
            st.error(f"Analysis failed: {e}")
            st.exception(e)

    # Visualization section
    if st.session_state.analysis_results is not None:
        results = st.session_state.analysis_results

        st.divider()
        st.subheader("5. Results")

        has_metadata = results.get("metadata") is not None
        tab_names = ["UMAP", "Spatial View", "3D Spatial", "PCA", "Variance Explained", "Gene Expression"]
        if not has_metadata:
            tab_names = ["UMAP", "PCA", "Variance Explained", "Gene Expression"]
        viz_tabs = st.tabs(tab_names)

        # UMAP tab
        with viz_tabs[0]:
            st.markdown("### Interactive UMAP")

            # Create DataFrame for plotting
            umap_df = pd.DataFrame({
                "UMAP1": results["X_umap"][:, 0],
                "UMAP2": results["X_umap"][:, 1],
                "Cell": results["cell_names"],
                "Cluster": [str(c) for c in results["clusters"]]
            })

            # Option to color by cluster, gene expression, or metadata
            color_options = ["Cluster"] + results["gene_names"]
            if has_metadata:
                meta_cols = results["metadata"].columns.tolist()
                color_options = ["Cluster"] + meta_cols + results["gene_names"]

            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                color_option = st.selectbox("Color by", color_options, key="umap_color")
            with col2:
                dot_size_umap = st.slider("Dot size", 1, 20, 6, key="umap_dot_size")
            with col3:
                color_scale_umap = st.radio("Scale", ["Linear", "Log"], key="umap_scale", horizontal=True)

            if color_option == "Cluster":
                fig = px.scatter(
                    umap_df, x="UMAP1", y="UMAP2", color="Cluster",
                    hover_data=["Cell"], title="UMAP colored by Cluster",
                    category_orders={"Cluster": sort_categories(umap_df["Cluster"])}
                )
            elif has_metadata and color_option in results["metadata"].columns:
                umap_df["Color"] = results["metadata"][color_option].values
                if umap_df["Color"].dtype == 'object':
                    sorted_cats = sort_categories(umap_df["Color"])
                    fig = px.scatter(umap_df, x="UMAP1", y="UMAP2", color="Color",
                                     hover_data=["Cell"], title=f"UMAP colored by {color_option}",
                                     category_orders={"Color": sorted_cats})
                else:
                    color_vals = umap_df["Color"].values.astype(float)
                    if color_scale_umap == "Log":
                        color_vals = np.log1p(np.maximum(color_vals, 0))
                    umap_df["ColorScaled"] = color_vals
                    fig = px.scatter(umap_df, x="UMAP1", y="UMAP2", color="ColorScaled",
                                     hover_data=["Cell", "Color"], title=f"UMAP colored by {color_option} ({color_scale_umap})",
                                     color_continuous_scale="Viridis")
            else:
                gene_idx = results["gene_names"].index(color_option)
                raw_expr = results["X_log"][:, gene_idx]
                if color_scale_umap == "Log":
                    color_vals = np.log1p(np.maximum(raw_expr, 0))
                else:
                    color_vals = raw_expr
                umap_df["Expression"] = color_vals
                umap_df["RawExpr"] = raw_expr
                fig = px.scatter(
                    umap_df, x="UMAP1", y="UMAP2", color="Expression",
                    hover_data=["Cell", "RawExpr"], title=f"UMAP colored by {color_option} ({color_scale_umap})",
                    color_continuous_scale="Viridis"
                )

            fig.update_traces(marker=dict(size=dot_size_umap))
            fig.update_layout(
                height=600,
                template="plotly_white",
                dragmode="pan"
            )

            # Enable scroll zoom
            config = {
                'scrollZoom': True,
                'displayModeBar': True,
                'modeBarButtonsToAdd': ['select2d', 'lasso2d']
            }

            st.plotly_chart(fig, use_container_width=True, config=config)

            # Download UMAP coordinates
            csv = umap_df.to_csv(index=False)
            st.download_button(
                "Download UMAP coordinates",
                csv,
                file_name="umap_coordinates.csv",
                mime="text/csv"
            )

        # Spatial View tab (side-by-side UMAP + spatial)
        if has_metadata:
            with viz_tabs[1]:
                st.markdown("### Side-by-Side: UMAP vs Spatial")

                meta_df = results["metadata"]
                # Try to find x, y columns
                x_cols = [c for c in meta_df.columns if c.lower() in ['x', 'x_coord', 'x_position', 'spatial_x']]
                y_cols = [c for c in meta_df.columns if c.lower() in ['y', 'y_coord', 'y_position', 'spatial_y']]

                if not x_cols or not y_cols:
                    x_cols = meta_df.select_dtypes(include=[np.number]).columns.tolist()
                    y_cols = x_cols

                col1, col2 = st.columns(2)
                with col1:
                    x_col = st.selectbox("X coordinate", x_cols if x_cols else meta_df.columns.tolist(), key="spatial_x")
                with col2:
                    y_col = st.selectbox("Y coordinate", y_cols if y_cols else meta_df.columns.tolist(), key="spatial_y",
                                         index=1 if len(y_cols) > 1 else 0)

                # Color and display options
                color_opts_spatial = ["Cluster"] + meta_df.columns.tolist() + results["gene_names"]
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    color_by_spatial = st.selectbox("Color by", color_opts_spatial, key="spatial_color")
                with col2:
                    dot_size_spatial = st.slider("Dot size", 1, 20, 6, key="spatial_dot_size")
                with col3:
                    color_scale_spatial = st.radio("Scale", ["Linear", "Log"], key="spatial_scale", horizontal=True)

                # Build spatial dataframe
                spatial_df = pd.DataFrame({
                    "x": meta_df[x_col].values,
                    "y": meta_df[y_col].values,
                    "Cell": results["cell_names"],
                    "Cluster": [str(c) for c in results["clusters"]],
                    "UMAP1": results["X_umap"][:, 0],
                    "UMAP2": results["X_umap"][:, 1],
                })

                # Add color column
                cat_order = None
                if color_by_spatial == "Cluster":
                    color_col = "Cluster"
                    is_categorical = True
                    cat_order = {"Cluster": sort_categories(spatial_df["Cluster"])}
                elif color_by_spatial in meta_df.columns:
                    spatial_df["Color"] = meta_df[color_by_spatial].values
                    color_col = "Color"
                    is_categorical = spatial_df["Color"].dtype == 'object'
                    if is_categorical:
                        cat_order = {"Color": sort_categories(spatial_df["Color"])}
                    elif color_scale_spatial == "Log":
                        spatial_df["ColorScaled"] = np.log1p(np.maximum(spatial_df["Color"].astype(float), 0))
                        color_col = "ColorScaled"
                else:
                    gene_idx = results["gene_names"].index(color_by_spatial)
                    raw_vals = results["X_log"][:, gene_idx]
                    if color_scale_spatial == "Log":
                        spatial_df["Color"] = np.log1p(np.maximum(raw_vals, 0))
                    else:
                        spatial_df["Color"] = raw_vals
                    color_col = "Color"
                    is_categorical = False

                # Create side-by-side plots
                plot_col1, plot_col2 = st.columns(2)

                with plot_col1:
                    if is_categorical:
                        fig1 = px.scatter(spatial_df, x="UMAP1", y="UMAP2", color=color_col,
                                          hover_data=["Cell"], title="UMAP",
                                          category_orders=cat_order)
                    else:
                        fig1 = px.scatter(spatial_df, x="UMAP1", y="UMAP2", color=color_col,
                                          hover_data=["Cell"], title=f"UMAP ({color_scale_spatial})",
                                          color_continuous_scale="Viridis")
                    fig1.update_traces(marker=dict(size=dot_size_spatial))
                    fig1.update_layout(height=500, template="plotly_white")
                    st.plotly_chart(fig1, use_container_width=True)

                with plot_col2:
                    if is_categorical:
                        fig2 = px.scatter(spatial_df, x="x", y="y", color=color_col,
                                          hover_data=["Cell"], title="Spatial Map",
                                          category_orders=cat_order)
                    else:
                        fig2 = px.scatter(spatial_df, x="x", y="y", color=color_col,
                                          hover_data=["Cell"], title=f"Spatial Map ({color_scale_spatial})",
                                          color_continuous_scale="Viridis")
                    fig2.update_traces(marker=dict(size=dot_size_spatial))
                    fig2.update_layout(height=500, template="plotly_white",
                                       xaxis_title=x_col, yaxis_title=y_col)
                    st.plotly_chart(fig2, use_container_width=True)

            # 3D Spatial tab
            with viz_tabs[2]:
                st.markdown("### 3D Spatial View")

                # Find z column
                z_cols = [c for c in meta_df.columns if c.lower() in ['z', 'z_coord', 'z_position', 'spatial_z']]
                if not z_cols:
                    z_cols = meta_df.select_dtypes(include=[np.number]).columns.tolist()

                col1, col2, col3 = st.columns(3)
                with col1:
                    x_col_3d = st.selectbox("X", meta_df.select_dtypes(include=[np.number]).columns.tolist(), key="3d_x")
                with col2:
                    y_col_3d = st.selectbox("Y", meta_df.select_dtypes(include=[np.number]).columns.tolist(), key="3d_y",
                                            index=min(1, len(meta_df.select_dtypes(include=[np.number]).columns)-1))
                with col3:
                    z_col_3d = st.selectbox("Z", meta_df.select_dtypes(include=[np.number]).columns.tolist(), key="3d_z",
                                            index=min(2, len(meta_df.select_dtypes(include=[np.number]).columns)-1))

                # Color and display options
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    color_by_3d = st.selectbox("Color by", color_opts_spatial, key="3d_color")
                with col2:
                    dot_size_3d = st.slider("Dot size", 1, 15, 3, key="3d_dot_size")
                with col3:
                    color_scale_3d = st.radio("Scale", ["Linear", "Log"], key="3d_scale", horizontal=True)

                # Build 3D dataframe
                df_3d = pd.DataFrame({
                    "x": meta_df[x_col_3d].values,
                    "y": meta_df[y_col_3d].values,
                    "z": meta_df[z_col_3d].values,
                    "Cell": results["cell_names"],
                    "Cluster": [str(c) for c in results["clusters"]],
                })

                cat_order_3d = None
                if color_by_3d == "Cluster":
                    color_col_3d = "Cluster"
                    is_cat_3d = True
                    cat_order_3d = {"Cluster": sort_categories(df_3d["Cluster"])}
                elif color_by_3d in meta_df.columns:
                    df_3d["Color"] = meta_df[color_by_3d].values
                    color_col_3d = "Color"
                    is_cat_3d = df_3d["Color"].dtype == 'object'
                    if is_cat_3d:
                        cat_order_3d = {"Color": sort_categories(df_3d["Color"])}
                    elif color_scale_3d == "Log":
                        df_3d["ColorScaled"] = np.log1p(np.maximum(df_3d["Color"].astype(float), 0))
                        color_col_3d = "ColorScaled"
                else:
                    gene_idx = results["gene_names"].index(color_by_3d)
                    raw_vals = results["X_log"][:, gene_idx]
                    if color_scale_3d == "Log":
                        df_3d["Color"] = np.log1p(np.maximum(raw_vals, 0))
                    else:
                        df_3d["Color"] = raw_vals
                    color_col_3d = "Color"
                    is_cat_3d = False

                if is_cat_3d:
                    fig_3d = px.scatter_3d(df_3d, x="x", y="y", z="z", color=color_col_3d,
                                           hover_data=["Cell"], title="3D Spatial Map",
                                           category_orders=cat_order_3d)
                else:
                    fig_3d = px.scatter_3d(df_3d, x="x", y="y", z="z", color=color_col_3d,
                                           hover_data=["Cell"], title=f"3D Spatial Map ({color_scale_3d})",
                                           color_continuous_scale="Viridis")

                fig_3d.update_traces(marker=dict(size=dot_size_3d))
                fig_3d.update_layout(height=700, template="plotly_white")
                st.plotly_chart(fig_3d, use_container_width=True)

        # PCA tab (index depends on whether metadata exists)
        pca_tab_idx = 3 if has_metadata else 1
        with viz_tabs[pca_tab_idx]:
            st.markdown("### PCA Plot")

            pc_x = st.selectbox("X axis", [f"PC{i+1}" for i in range(results["X_pca"].shape[1])], index=0)
            pc_y = st.selectbox("Y axis", [f"PC{i+1}" for i in range(results["X_pca"].shape[1])], index=1)

            pc_x_idx = int(pc_x[2:]) - 1
            pc_y_idx = int(pc_y[2:]) - 1

            pca_df = pd.DataFrame({
                pc_x: results["X_pca"][:, pc_x_idx],
                pc_y: results["X_pca"][:, pc_y_idx],
                "Cell": results["cell_names"]
            })

            var_x = results["variance_explained"][pc_x_idx] * 100
            var_y = results["variance_explained"][pc_y_idx] * 100

            fig = px.scatter(
                pca_df,
                x=pc_x,
                y=pc_y,
                hover_data=["Cell"],
                title=f"PCA: {pc_x} ({var_x:.1f}%) vs {pc_y} ({var_y:.1f}%)"
            )

            fig.update_traces(marker=dict(size=8))
            fig.update_layout(height=600, template="plotly_white")

            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

        # Variance explained tab
        var_tab_idx = 4 if has_metadata else 2
        with viz_tabs[var_tab_idx]:
            st.markdown("### Variance Explained by PCs")

            var_df = pd.DataFrame({
                "PC": [f"PC{i+1}" for i in range(len(results["variance_explained"]))],
                "Variance Explained (%)": results["variance_explained"] * 100,
                "Cumulative (%)": np.cumsum(results["variance_explained"]) * 100
            })

            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=var_df["PC"],
                y=var_df["Variance Explained (%)"],
                name="Individual",
                marker_color="steelblue"
            ))

            fig.add_trace(go.Scatter(
                x=var_df["PC"],
                y=var_df["Cumulative (%)"],
                name="Cumulative",
                mode="lines+markers",
                marker_color="coral"
            ))

            fig.update_layout(
                title="Scree Plot",
                xaxis_title="Principal Component",
                yaxis_title="Variance Explained (%)",
                height=500,
                template="plotly_white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02)
            )

            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(var_df, use_container_width=True, hide_index=True)

        # Gene expression tab
        gene_tab_idx = 5 if has_metadata else 3
        with viz_tabs[gene_tab_idx]:
            st.markdown("### Gene Expression Viewer")

            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                selected_genes = st.multiselect(
                    "Select genes to visualize",
                    results["gene_names"],
                    default=results["gene_names"][:3] if len(results["gene_names"]) >= 3 else results["gene_names"]
                )
            with col2:
                group_by_cluster = st.checkbox("Group by cluster", value=True, key="heatmap_group")
            with col3:
                expr_scale = st.radio("Data scale", ["Log", "Raw"], key="expr_scale", horizontal=True)

            if selected_genes:
                # Create expression matrix for selected genes
                gene_indices = [results["gene_names"].index(g) for g in selected_genes]

                # Get data based on scale selection
                if expr_scale == "Log":
                    expr_subset = results["X_log"][:, gene_indices]
                    scale_label = "log(count+1)"
                else:
                    # Convert back to raw counts: expm1 is inverse of log1p
                    expr_subset = np.expm1(results["X_log"][:, gene_indices])
                    scale_label = "Raw count"

                expr_df = pd.DataFrame(
                    expr_subset,
                    columns=selected_genes,
                    index=results["cell_names"]
                )
                expr_df["Cluster"] = [str(c) for c in results["clusters"]]

                # Sort by cluster if requested
                if group_by_cluster:
                    sorted_clusters = sort_categories(expr_df["Cluster"])
                    expr_df["Cluster_sort"] = expr_df["Cluster"].apply(lambda x: sorted_clusters.index(x))
                    expr_df = expr_df.sort_values("Cluster_sort")
                    expr_df = expr_df.drop(columns=["Cluster_sort"])

                # Get cluster info for annotation
                cluster_labels = expr_df["Cluster"].values
                expr_df_plot = expr_df.drop(columns=["Cluster"])

                # Create cluster color mapping
                unique_clusters = sort_categories(cluster_labels)
                colors = px.colors.qualitative.Set2 + px.colors.qualitative.Set3
                cluster_colors = {c: colors[i % len(colors)] for i, c in enumerate(unique_clusters)}

                # Heatmap with cluster color bar
                if group_by_cluster:
                    from plotly.subplots import make_subplots

                    # Create subplots: cluster bar on top, heatmap below
                    fig = make_subplots(
                        rows=2, cols=1,
                        row_heights=[0.05, 0.95],
                        vertical_spacing=0.02,
                        shared_xaxes=True
                    )

                    # Add cluster color bar (as a heatmap with 1 row)
                    cluster_numeric = [unique_clusters.index(c) for c in cluster_labels]
                    fig.add_trace(
                        go.Heatmap(
                            z=[cluster_numeric],
                            colorscale=[[i/(len(unique_clusters)-1) if len(unique_clusters) > 1 else 0, cluster_colors[c]]
                                       for i, c in enumerate(unique_clusters)],
                            showscale=False,
                            hovertemplate="Cluster: %{customdata}<extra></extra>",
                            customdata=[[c for c in cluster_labels]]
                        ),
                        row=1, col=1
                    )

                    # Add main heatmap (reverse gene order to match violin plot - first gene at top)
                    genes_reversed = list(reversed(selected_genes))
                    z_reversed = expr_df_plot.T.values[::-1]  # Reverse rows to match gene order
                    fig.add_trace(
                        go.Heatmap(
                            z=z_reversed,
                            x=list(range(len(expr_df_plot))),
                            y=genes_reversed,
                            colorscale="Viridis",
                            colorbar=dict(
                                title=dict(text=scale_label, side="top"),
                                orientation="h",
                                len=0.3,
                                x=0.85,
                                y=1.15,
                                xanchor="center",
                                yanchor="bottom",
                                thickness=15
                            ),
                            hovertemplate="Cell: %{x}<br>Gene: %{y}<br>Expression: %{z:.2f}<extra></extra>"
                        ),
                        row=2, col=1
                    )

                    # Add cluster boundary lines and labels
                    cluster_positions = []
                    current_cluster = cluster_labels[0]
                    start_idx = 0
                    for i, c in enumerate(cluster_labels):
                        if c != current_cluster:
                            cluster_positions.append((start_idx, i-1, current_cluster))
                            current_cluster = c
                            start_idx = i
                    cluster_positions.append((start_idx, len(cluster_labels)-1, current_cluster))

                    # Add vertical lines at cluster boundaries
                    shapes = []
                    for start, end, cluster in cluster_positions[:-1]:
                        shapes.append(dict(
                            type="line", x0=end+0.5, x1=end+0.5, y0=0, y1=1,
                            xref="x2", yref="paper",
                            line=dict(color="white", width=1)
                        ))

                    fig.update_layout(
                        title=dict(text=f"Gene Expression Heatmap - {scale_label} (grouped by cluster)", font=dict(size=16)),
                        height=max(400, len(selected_genes) * 35 + 80),
                        shapes=shapes
                    )
                    fig.update_xaxes(showticklabels=False, row=1, col=1)
                    fig.update_yaxes(showticklabels=False, row=1, col=1)
                    fig.update_xaxes(title="Cells (colored by cluster above)", row=2, col=1)
                    fig.update_yaxes(title="Genes", row=2, col=1)

                    # Add legend for clusters
                    for i, c in enumerate(unique_clusters):
                        fig.add_trace(go.Scatter(
                            x=[None], y=[None], mode='markers',
                            marker=dict(size=10, color=cluster_colors[c]),
                            name=f"Cluster {c}", showlegend=True
                        ))

                else:
                    # Reverse gene order to match violin plot - first gene at top
                    genes_reversed_simple = list(reversed(selected_genes))
                    fig = px.imshow(
                        expr_df_plot[genes_reversed_simple].T,
                        labels=dict(x="Cells", y="Genes", color=scale_label),
                        aspect="auto",
                        color_continuous_scale="Viridis"
                    )
                    fig.update_layout(
                        title=dict(text=f"Gene Expression Heatmap - {scale_label}", font=dict(size=16)),
                        height=max(300, len(selected_genes) * 30)
                    )

                st.plotly_chart(fig, use_container_width=True)

                # Distribution plot grouped by cluster
                st.markdown(f"#### Expression Distribution by Cluster ({scale_label})")

                # Prepare data with cluster info
                expr_df_melt = expr_df_plot.copy()
                expr_df_melt["Cluster"] = cluster_labels
                melt_df = expr_df_melt.melt(id_vars=["Cluster"], var_name="Gene", value_name=scale_label)
                melt_df["Cluster"] = melt_df["Cluster"].astype(str)

                # Create violin plots with one row per gene (faceted)
                # Gene order: first gene at top (matches heatmap which is now also first gene at top)
                fig = px.violin(
                    melt_df,
                    x="Cluster",
                    y=scale_label,
                    color="Cluster",
                    facet_row="Gene",
                    box=True,
                    category_orders={"Cluster": unique_clusters, "Gene": selected_genes},
                    color_discrete_map=cluster_colors
                )

                # Update layout for stacked rows
                fig.update_layout(
                    title=dict(text=f"Expression Distribution by Cluster ({scale_label})", font=dict(size=16)),
                    height=max(250, len(selected_genes) * 180),
                    template="plotly_white",
                    legend_title="Cluster",
                    showlegend=True
                )

                # Move gene labels to the left side
                fig.for_each_annotation(lambda a: a.update(
                    text=a.text.split("=")[-1],
                    x=-0.07,
                    xanchor="right",
                    textangle=0
                ))
                fig.update_yaxes(matches=None, title_text=scale_label)  # Show y-axis label
                fig.update_xaxes(title_text="")

                # Add left margin for gene labels
                fig.update_layout(margin=dict(l=100))

                st.plotly_chart(fig, use_container_width=True)

        # Export section
        st.divider()
        st.subheader("6. Export Results")

        col1, col2, col3 = st.columns(3)

        with col1:
            # Export log-transformed data
            log_df = pd.DataFrame(
                results["X_log"],
                index=results["cell_names"],
                columns=results["gene_names"]
            )
            csv = log_df.to_csv()
            st.download_button(
                "Download Log-transformed Data",
                csv,
                file_name="log_transformed_data.csv",
                mime="text/csv"
            )

        with col2:
            # Export scaled data
            scaled_df = pd.DataFrame(
                results["X_scaled"],
                index=results["cell_names"],
                columns=results["gene_names"]
            )
            csv = scaled_df.to_csv()
            st.download_button(
                "Download Scaled Data",
                csv,
                file_name="scaled_data.csv",
                mime="text/csv"
            )

        with col3:
            # Export PCA coordinates
            pca_df = pd.DataFrame(
                results["X_pca"],
                index=results["cell_names"],
                columns=[f"PC{i+1}" for i in range(results["X_pca"].shape[1])]
            )
            csv = pca_df.to_csv()
            st.download_button(
                "Download PCA Coordinates",
                csv,
                file_name="pca_coordinates.csv",
                mime="text/csv"
            )

else:
    st.info("Upload a data file to begin analysis")

    with st.expander("Expected file format"):
        st.markdown("""
        **Supported formats:** Excel (.xlsx, .xls), CSV (.csv), Tab-delimited (.txt, .tsv)

        ---

        **Gene Expression Data:**
        - **Rows**: Cells (first column = cell names/IDs)
        - **Columns**: Genes (header row = gene names)
        - **Values**: Raw mRNA transcript counts (integers or floats)

        Example:
        | Cell_ID | Gene_A | Gene_B | Gene_C |
        |---------|--------|--------|--------|
        | Cell_1  | 10     | 0      | 25     |
        | Cell_2  | 5      | 12     | 8      |
        | Cell_3  | 0      | 3      | 15     |

        ---

        **Cell Metadata (Optional):**
        - **Rows**: Cells (first column = cell names/IDs, must match expression data)
        - **Columns**: Features such as spatial coordinates, morphology measurements, or annotations
        - **Values**: Numeric (for coordinates/measurements) or categorical (for annotations)

        Example:
        | Cell_ID | x      | y      | z      | area   | cell_type   |
        |---------|--------|--------|--------|--------|-------------|
        | Cell_1  | 102.5  | 245.3  | 1.0    | 156.2  | neuron      |
        | Cell_2  | 98.7   | 312.1  | 2.0    | 203.8  | astrocyte   |
        | Cell_3  | 150.2  | 189.6  | 1.0    | 178.4  | neuron      |

        **Recognized coordinate columns:** x, y, z, x_coord, y_coord, z_coord, x_position, y_position, z_position, spatial_x, spatial_y, spatial_z

        **Note:** Cell IDs in the metadata must match those in the expression data for proper merging.
        """)
