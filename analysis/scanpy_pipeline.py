"""Scanpy analysis pipeline for single-cell RNA-seq data."""

import scanpy as sc
import anndata as ad
import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass


@dataclass
class QCMetrics:
    """Quality control metrics."""
    n_cells_before: int
    n_cells_after: int
    n_genes_before: int
    n_genes_after: int
    median_genes_per_cell: float
    median_counts_per_cell: float
    pct_mito_median: float


class ScanpyPipeline:
    """Complete Scanpy analysis pipeline."""

    def __init__(self, adata: ad.AnnData, use_raw: bool = True):
        """Initialize pipeline with AnnData object.

        Args:
            adata: AnnData object (can contain raw or processed data)
            use_raw: Whether to attempt to find and use raw counts
        """
        self.adata = adata.copy()
        self.history: List[Dict] = []
        self.data_source = "X"  # Track where we got the data from

        if use_raw:
            self._initialize_from_raw()

    def _initialize_from_raw(self) -> None:
        """Find and use raw counts if available."""
        import scipy.sparse as sp

        # Check if current X looks like raw counts (non-negative integers)
        if sp.issparse(self.adata.X):
            sample = self.adata.X[:100, :100].toarray()
        else:
            sample = self.adata.X[:100, :100]

        has_negative = (sample < 0).any()
        is_integer_like = np.allclose(sample, np.round(sample), rtol=0.01, atol=0.01, equal_nan=True)

        # If X has negative values or non-integers, look for raw counts elsewhere
        if has_negative or not is_integer_like:
            raw_found = False

            # Check .raw attribute
            if self.adata.raw is not None:
                print("Using counts from .raw")
                self.adata = self.adata.raw.to_adata()
                self.data_source = "raw"
                raw_found = True

            # Check common layer names for raw counts
            elif "counts" in self.adata.layers:
                print("Using counts from .layers['counts']")
                self.adata.X = self.adata.layers["counts"].copy()
                self.data_source = "layers['counts']"
                raw_found = True

            elif "raw_counts" in self.adata.layers:
                print("Using counts from .layers['raw_counts']")
                self.adata.X = self.adata.layers["raw_counts"].copy()
                self.data_source = "layers['raw_counts']"
                raw_found = True

            elif "spliced" in self.adata.layers:
                # For RNA velocity data
                print("Using counts from .layers['spliced']")
                self.adata.X = self.adata.layers["spliced"].copy()
                self.data_source = "layers['spliced']"
                raw_found = True

            if not raw_found:
                print("WARNING: Data appears to be already processed (has negative values).")
                print("No raw counts found in .raw or .layers. Using X as-is.")
                print("Available layers:", list(self.adata.layers.keys()) if self.adata.layers else "None")
        else:
            print("Data in .X appears to be raw counts (non-negative integers)")

    def _log_step(self, step: str, params: Dict) -> None:
        """Log analysis step."""
        self.history.append({"step": step, "params": params})

    def calculate_qc_metrics(
        self,
        mito_prefix: str = "mt-",
    ) -> QCMetrics:
        """Calculate QC metrics without filtering.

        Args:
            mito_prefix: Prefix for mitochondrial genes

        Returns:
            QCMetrics object
        """
        # Calculate mitochondrial gene percentage
        self.adata.var["mt"] = self.adata.var_names.str.lower().str.startswith(mito_prefix.lower())
        sc.pp.calculate_qc_metrics(
            self.adata,
            qc_vars=["mt"],
            percent_top=None,
            log1p=False,
            inplace=True
        )

        return QCMetrics(
            n_cells_before=self.adata.n_obs,
            n_cells_after=self.adata.n_obs,
            n_genes_before=self.adata.n_vars,
            n_genes_after=self.adata.n_vars,
            median_genes_per_cell=np.median(self.adata.obs["n_genes_by_counts"]),
            median_counts_per_cell=np.median(self.adata.obs["total_counts"]),
            pct_mito_median=np.median(self.adata.obs["pct_counts_mt"]),
        )

    def filter_cells(
        self,
        min_genes: int = 200,
        max_genes: Optional[int] = None,
        min_counts: Optional[int] = None,
        max_counts: Optional[int] = None,
        max_pct_mito: float = 20.0,
    ) -> QCMetrics:
        """Filter cells based on QC metrics.

        Args:
            min_genes: Minimum genes per cell
            max_genes: Maximum genes per cell
            min_counts: Minimum counts per cell
            max_counts: Maximum counts per cell
            max_pct_mito: Maximum mitochondrial percentage

        Returns:
            QCMetrics after filtering
        """
        n_cells_before = self.adata.n_obs
        n_genes_before = self.adata.n_vars

        # Filter by gene counts
        sc.pp.filter_cells(self.adata, min_genes=min_genes)

        if max_genes and self.adata.n_obs > 0:
            self.adata = self.adata[self.adata.obs["n_genes_by_counts"] < max_genes, :].copy()

        if min_counts and self.adata.n_obs > 0:
            self.adata = self.adata[self.adata.obs["total_counts"] > min_counts, :].copy()

        if max_counts and self.adata.n_obs > 0:
            self.adata = self.adata[self.adata.obs["total_counts"] < max_counts, :].copy()

        # Filter by mito percentage
        if "pct_counts_mt" in self.adata.obs.columns and self.adata.n_obs > 0:
            self.adata = self.adata[self.adata.obs["pct_counts_mt"] < max_pct_mito, :].copy()

        # Ensure we have cells left
        if self.adata.n_obs == 0:
            raise ValueError("All cells were filtered out. Please adjust QC thresholds.")

        self._log_step("filter_cells", {
            "min_genes": min_genes,
            "max_genes": max_genes,
            "max_pct_mito": max_pct_mito,
        })

        return QCMetrics(
            n_cells_before=n_cells_before,
            n_cells_after=self.adata.n_obs,
            n_genes_before=n_genes_before,
            n_genes_after=self.adata.n_vars,
            median_genes_per_cell=np.median(self.adata.obs["n_genes_by_counts"]),
            median_counts_per_cell=np.median(self.adata.obs["total_counts"]),
            pct_mito_median=np.median(self.adata.obs.get("pct_counts_mt", [0])),
        )

    def filter_genes(
        self,
        min_cells: int = 3,
    ) -> int:
        """Filter genes expressed in too few cells.

        Args:
            min_cells: Minimum cells expressing gene

        Returns:
            Number of genes after filtering
        """
        n_before = self.adata.n_vars
        sc.pp.filter_genes(self.adata, min_cells=min_cells)

        # Ensure we have genes left
        if self.adata.n_vars == 0:
            raise ValueError("All genes were filtered out. Please adjust min_cells threshold.")

        self._log_step("filter_genes", {"min_cells": min_cells})

        return self.adata.n_vars

    def normalize(
        self,
        target_sum: float = 10000,
        log_transform: bool = True,
    ) -> None:
        """Normalize counts.

        Args:
            target_sum: Target sum for normalization
            log_transform: Whether to log1p transform
        """
        import scipy.sparse as sp

        # Store raw counts
        self.adata.layers["counts"] = self.adata.X.copy()

        # Normalize
        sc.pp.normalize_total(self.adata, target_sum=target_sum)

        if log_transform:
            sc.pp.log1p(self.adata)

        # Handle any NaN/Inf values that might have been introduced
        if sp.issparse(self.adata.X):
            X_dense = self.adata.X.toarray()
            if np.isnan(X_dense).any() or np.isinf(X_dense).any():
                X_dense = np.nan_to_num(X_dense, nan=0.0, posinf=0.0, neginf=0.0)
                self.adata.X = sp.csr_matrix(X_dense)
        else:
            if np.isnan(self.adata.X).any() or np.isinf(self.adata.X).any():
                self.adata.X = np.nan_to_num(self.adata.X, nan=0.0, posinf=0.0, neginf=0.0)

        self._log_step("normalize", {
            "target_sum": target_sum,
            "log_transform": log_transform,
        })

    def find_variable_genes(
        self,
        n_top_genes: int = 2000,
        flavor: str = "seurat",
        batch_key: Optional[str] = None,
    ) -> List[str]:
        """Identify highly variable genes.

        Args:
            n_top_genes: Number of top variable genes
            flavor: Method for finding HVGs ('seurat', 'cell_ranger', or 'seurat_v3')
            batch_key: Batch key for batch-aware HVG selection

        Returns:
            List of highly variable gene names
        """
        # Adjust n_top_genes if we have fewer genes than requested
        n_top_genes = min(n_top_genes, self.adata.n_vars - 1)
        if n_top_genes < 100:
            raise ValueError(f"Not enough genes ({self.adata.n_vars}) to find highly variable genes. Need at least 100.")

        try:
            # Try seurat_v3 with counts layer first (requires raw counts)
            if flavor == "seurat_v3" and "counts" in self.adata.layers:
                sc.pp.highly_variable_genes(
                    self.adata,
                    n_top_genes=n_top_genes,
                    flavor="seurat_v3",
                    batch_key=batch_key,
                    layer="counts",
                )
            else:
                # Fall back to seurat method (works on log-normalized data)
                sc.pp.highly_variable_genes(
                    self.adata,
                    n_top_genes=n_top_genes,
                    flavor="seurat",
                    batch_key=batch_key,
                )
        except Exception as e:
            # If seurat fails, try cell_ranger method
            print(f"HVG selection with {flavor} failed: {e}, trying cell_ranger method")
            try:
                sc.pp.highly_variable_genes(
                    self.adata,
                    n_top_genes=n_top_genes,
                    flavor="cell_ranger",
                    batch_key=batch_key,
                )
            except Exception as e2:
                # Last resort: mark top genes by variance as highly variable
                print(f"cell_ranger method also failed: {e2}, using variance-based selection")
                import scipy.sparse as sp
                if sp.issparse(self.adata.X):
                    variances = np.array(self.adata.X.power(2).mean(axis=0) - np.power(self.adata.X.mean(axis=0), 2)).flatten()
                else:
                    variances = np.var(self.adata.X, axis=0)
                top_indices = np.argsort(variances)[-n_top_genes:]
                self.adata.var["highly_variable"] = False
                self.adata.var.iloc[top_indices, self.adata.var.columns.get_loc("highly_variable")] = True

        self._log_step("find_variable_genes", {
            "n_top_genes": n_top_genes,
            "flavor": flavor,
        })

        hvg_mask = self.adata.var["highly_variable"]
        return list(self.adata.var_names[hvg_mask])

    def scale(
        self,
        max_value: float = 10,
    ) -> None:
        """Scale gene expression.

        Args:
            max_value: Maximum value after scaling
        """
        import scipy.sparse as sp

        # Filter out zero-variance genes before scaling to prevent NaN
        if sp.issparse(self.adata.X):
            gene_vars = np.array(self.adata.X.power(2).mean(axis=0) - np.power(self.adata.X.mean(axis=0), 2)).flatten()
        else:
            gene_vars = np.var(self.adata.X, axis=0)

        # Keep genes with non-zero variance
        nonzero_var = gene_vars > 1e-10
        if not nonzero_var.all():
            n_removed = (~nonzero_var).sum()
            print(f"Removing {n_removed} zero-variance genes before scaling")
            self.adata = self.adata[:, nonzero_var].copy()

        sc.pp.scale(self.adata, max_value=max_value)

        # Handle any remaining NaN values
        if sp.issparse(self.adata.X):
            X_dense = self.adata.X.toarray()
            if np.isnan(X_dense).any():
                X_dense = np.nan_to_num(X_dense, nan=0.0)
                self.adata.X = sp.csr_matrix(X_dense)
        else:
            if np.isnan(self.adata.X).any():
                self.adata.X = np.nan_to_num(self.adata.X, nan=0.0)

        self._log_step("scale", {"max_value": max_value})

    def run_pca(
        self,
        n_comps: int = 50,
        use_highly_variable: bool = True,
    ) -> None:
        """Run PCA.

        Args:
            n_comps: Number of components
            use_highly_variable: Use only HVGs
        """
        sc.tl.pca(
            self.adata,
            n_comps=n_comps,
            use_highly_variable=use_highly_variable,
        )
        self._log_step("pca", {"n_comps": n_comps})

    def compute_neighbors(
        self,
        n_neighbors: int = 15,
        n_pcs: int = 50,
    ) -> None:
        """Compute neighborhood graph.

        Args:
            n_neighbors: Number of neighbors
            n_pcs: Number of PCs to use
        """
        sc.pp.neighbors(
            self.adata,
            n_neighbors=n_neighbors,
            n_pcs=n_pcs,
        )
        self._log_step("neighbors", {
            "n_neighbors": n_neighbors,
            "n_pcs": n_pcs,
        })

    def run_umap(
        self,
        min_dist: float = 0.5,
        spread: float = 1.0,
    ) -> None:
        """Run UMAP.

        Args:
            min_dist: Minimum distance parameter
            spread: Spread parameter
        """
        sc.tl.umap(self.adata, min_dist=min_dist, spread=spread)
        self._log_step("umap", {"min_dist": min_dist, "spread": spread})

    def run_tsne(
        self,
        perplexity: float = 30,
    ) -> None:
        """Run t-SNE.

        Args:
            perplexity: Perplexity parameter
        """
        sc.tl.tsne(self.adata, perplexity=perplexity)
        self._log_step("tsne", {"perplexity": perplexity})

    def cluster(
        self,
        resolution: float = 1.0,
        algorithm: str = "leiden",
    ) -> int:
        """Perform clustering.

        Args:
            resolution: Resolution parameter
            algorithm: 'leiden' or 'louvain'

        Returns:
            Number of clusters
        """
        if algorithm == "leiden":
            sc.tl.leiden(self.adata, resolution=resolution)
        else:
            sc.tl.louvain(self.adata, resolution=resolution)

        n_clusters = len(self.adata.obs[algorithm].unique())
        self._log_step("cluster", {
            "algorithm": algorithm,
            "resolution": resolution,
            "n_clusters": n_clusters,
        })

        return n_clusters

    def find_markers(
        self,
        groupby: str = "leiden",
        method: str = "wilcoxon",
        n_genes: int = 25,
    ) -> pd.DataFrame:
        """Find marker genes for each cluster.

        Args:
            groupby: Column to group by
            method: Statistical method
            n_genes: Number of top genes per cluster

        Returns:
            DataFrame with marker genes
        """
        sc.tl.rank_genes_groups(
            self.adata,
            groupby=groupby,
            method=method,
            n_genes=n_genes,
        )

        self._log_step("find_markers", {
            "groupby": groupby,
            "method": method,
            "n_genes": n_genes,
        })

        # Extract results to DataFrame
        result = self.adata.uns["rank_genes_groups"]
        groups = result["names"].dtype.names

        markers_list = []
        for group in groups:
            for i in range(n_genes):
                markers_list.append({
                    "cluster": group,
                    "gene": result["names"][group][i],
                    "score": result["scores"][group][i],
                    "pval": result["pvals"][group][i],
                    "pval_adj": result["pvals_adj"][group][i],
                    "logfoldchange": result["logfoldchanges"][group][i],
                })

        return pd.DataFrame(markers_list)

    def run_full_pipeline(
        self,
        min_genes: int = 200,
        max_pct_mito: float = 20.0,
        n_top_genes: int = 2000,
        n_pcs: int = 50,
        n_neighbors: int = 15,
        resolution: float = 1.0,
    ) -> Dict[str, Any]:
        """Run complete analysis pipeline.

        Args:
            min_genes: Minimum genes per cell
            max_pct_mito: Maximum mito percentage
            n_top_genes: Number of HVGs
            n_pcs: Number of PCs
            n_neighbors: Number of neighbors
            resolution: Clustering resolution

        Returns:
            Dict with analysis results
        """
        results = {}

        # QC
        self.calculate_qc_metrics()
        results["qc_before"] = self.filter_cells(
            min_genes=min_genes,
            max_pct_mito=max_pct_mito,
        )

        # Filter genes
        self.filter_genes(min_cells=3)

        # Normalize
        self.normalize()

        # Find variable genes
        results["hvgs"] = self.find_variable_genes(n_top_genes=n_top_genes)

        # Scale
        self.scale()

        # PCA
        self.run_pca(n_comps=n_pcs)

        # Neighbors
        self.compute_neighbors(n_neighbors=n_neighbors, n_pcs=n_pcs)

        # UMAP
        self.run_umap()

        # Clustering
        results["n_clusters"] = self.cluster(resolution=resolution)

        # Markers
        results["markers"] = self.find_markers()

        return results

    def get_adata(self) -> ad.AnnData:
        """Get the processed AnnData object."""
        return self.adata
