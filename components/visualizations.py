"""Visualization components for the Research Analysis Platform."""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from typing import Optional, List
import anndata as ad


def plot_umap(
    adata: ad.AnnData,
    color_by: str = "leiden",
    title: str = "UMAP Visualization",
    point_size: int = 5,
    width: int = 800,
    height: int = 600,
) -> go.Figure:
    """Create interactive UMAP plot using Plotly."""
    if "X_umap" not in adata.obsm:
        st.error("UMAP coordinates not found. Please run UMAP first.")
        return None

    # Prepare data
    umap_coords = adata.obsm["X_umap"]
    df = pd.DataFrame({
        "UMAP1": umap_coords[:, 0],
        "UMAP2": umap_coords[:, 1],
    })

    # Add color column
    if color_by in adata.obs.columns:
        df[color_by] = adata.obs[color_by].values
    elif color_by in adata.var_names:
        # Gene expression
        gene_idx = adata.var_names.get_loc(color_by)
        if hasattr(adata.X, "toarray"):
            df[color_by] = adata.X[:, gene_idx].toarray().flatten()
        else:
            df[color_by] = adata.X[:, gene_idx].flatten()

    # Create plot
    if df[color_by].dtype == "object" or df[color_by].dtype.name == "category":
        fig = px.scatter(
            df,
            x="UMAP1",
            y="UMAP2",
            color=color_by,
            title=title,
            width=width,
            height=height,
        )
    else:
        fig = px.scatter(
            df,
            x="UMAP1",
            y="UMAP2",
            color=color_by,
            title=title,
            width=width,
            height=height,
            color_continuous_scale="Viridis",
        )

    fig.update_traces(marker=dict(size=point_size))
    fig.update_layout(
        template="plotly_white",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
    )

    return fig


def plot_violin(
    adata: ad.AnnData,
    genes: List[str],
    groupby: str = "leiden",
    title: str = "Gene Expression",
    width: int = 800,
    height: int = 500,
) -> go.Figure:
    """Create violin plot for gene expression."""
    # Filter valid genes
    valid_genes = [g for g in genes if g in adata.var_names]
    if not valid_genes:
        st.error("No valid genes found in the dataset.")
        return None

    # Prepare data
    data = []
    for gene in valid_genes:
        gene_idx = adata.var_names.get_loc(gene)
        if hasattr(adata.X, "toarray"):
            expr = adata.X[:, gene_idx].toarray().flatten()
        else:
            expr = adata.X[:, gene_idx].flatten()

        for group in adata.obs[groupby].unique():
            mask = adata.obs[groupby] == group
            data.append({
                "Gene": gene,
                "Group": str(group),
                "Expression": expr[mask].tolist(),
            })

    # Create figure with subplots
    fig = go.Figure()

    colors = px.colors.qualitative.Set2
    for i, gene in enumerate(valid_genes):
        gene_data = [d for d in data if d["Gene"] == gene]
        for j, gd in enumerate(gene_data):
            fig.add_trace(go.Violin(
                y=gd["Expression"],
                name=f"{gene} - {gd['Group']}",
                legendgroup=gene,
                scalegroup=gene,
                line_color=colors[i % len(colors)],
                showlegend=(j == 0),
            ))

    fig.update_layout(
        title=title,
        width=width,
        height=height,
        template="plotly_white",
        violinmode="group",
    )

    return fig


def plot_dotplot(
    adata: ad.AnnData,
    genes: List[str],
    groupby: str = "leiden",
    title: str = "Dot Plot",
    width: int = 800,
    height: int = 500,
) -> go.Figure:
    """Create dot plot for gene expression across groups."""
    valid_genes = [g for g in genes if g in adata.var_names]
    if not valid_genes:
        st.error("No valid genes found.")
        return None

    groups = adata.obs[groupby].unique()

    # Calculate mean expression and fraction expressing
    mean_expr = []
    frac_expr = []

    for gene in valid_genes:
        gene_idx = adata.var_names.get_loc(gene)
        if hasattr(adata.X, "toarray"):
            expr = adata.X[:, gene_idx].toarray().flatten()
        else:
            expr = adata.X[:, gene_idx].flatten()

        gene_means = []
        gene_fracs = []
        for group in groups:
            mask = adata.obs[groupby] == group
            group_expr = expr[mask]
            gene_means.append(np.mean(group_expr))
            gene_fracs.append(np.sum(group_expr > 0) / len(group_expr) * 100)

        mean_expr.append(gene_means)
        frac_expr.append(gene_fracs)

    # Create dot plot
    fig = go.Figure()

    for i, gene in enumerate(valid_genes):
        for j, group in enumerate(groups):
            fig.add_trace(go.Scatter(
                x=[str(group)],
                y=[gene],
                mode="markers",
                marker=dict(
                    size=frac_expr[i][j] / 5 + 5,  # Scale size
                    color=mean_expr[i][j],
                    colorscale="Viridis",
                    showscale=(i == 0 and j == 0),
                    colorbar=dict(title="Mean Expr"),
                ),
                showlegend=False,
                hovertemplate=f"Gene: {gene}<br>Group: {group}<br>Mean: {mean_expr[i][j]:.2f}<br>% Expressing: {frac_expr[i][j]:.1f}%",
            ))

    fig.update_layout(
        title=title,
        width=width,
        height=height,
        template="plotly_white",
        xaxis_title=groupby,
        yaxis_title="Genes",
    )

    return fig


def plot_heatmap(
    adata: ad.AnnData,
    genes: List[str],
    groupby: str = "leiden",
    title: str = "Expression Heatmap",
    width: int = 800,
    height: int = 600,
) -> go.Figure:
    """Create heatmap of gene expression."""
    valid_genes = [g for g in genes if g in adata.var_names]
    if not valid_genes:
        st.error("No valid genes found.")
        return None

    groups = sorted(adata.obs[groupby].unique())

    # Calculate mean expression per group
    z_data = []
    for gene in valid_genes:
        gene_idx = adata.var_names.get_loc(gene)
        if hasattr(adata.X, "toarray"):
            expr = adata.X[:, gene_idx].toarray().flatten()
        else:
            expr = adata.X[:, gene_idx].flatten()

        gene_means = []
        for group in groups:
            mask = adata.obs[groupby] == group
            gene_means.append(np.mean(expr[mask]))
        z_data.append(gene_means)

    # Z-score normalize
    z_data = np.array(z_data)
    z_data = (z_data - z_data.mean(axis=1, keepdims=True)) / (z_data.std(axis=1, keepdims=True) + 1e-10)

    fig = go.Figure(data=go.Heatmap(
        z=z_data,
        x=[str(g) for g in groups],
        y=valid_genes,
        colorscale="RdBu_r",
        zmid=0,
        colorbar=dict(title="Z-score"),
    ))

    fig.update_layout(
        title=title,
        width=width,
        height=height,
        template="plotly_white",
        xaxis_title=groupby,
        yaxis_title="Genes",
    )

    return fig
