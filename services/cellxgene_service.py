"""CELLxGENE Census service for searching and fetching single-cell data."""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import pandas as pd


@dataclass
class DatasetInfo:
    """Information about a CELLxGENE dataset."""
    dataset_id: str
    title: str
    description: str
    organism: str
    tissue: str
    cell_count: int
    assay: str


class CellxGeneService:
    """Service for interacting with CELLxGENE Census."""

    def __init__(self, census_version: str = "stable"):
        """Initialize CELLxGENE service.

        Args:
            census_version: Census version to use
        """
        self.census_version = census_version
        self._census = None

    def _get_census(self):
        """Lazy load census connection."""
        if self._census is None:
            import cellxgene_census
            self._census = cellxgene_census.open_soma(census_version=self.census_version)
        return self._census

    def get_available_tissues(self, organism: str = "Homo sapiens") -> List[str]:
        """Get list of available tissues.

        Args:
            organism: Species name

        Returns:
            List of tissue names
        """
        try:
            census = self._get_census()
            obs = census["census_data"][organism].obs
            tissues = obs.read(column_names=["tissue"]).concat().to_pandas()["tissue"].unique()
            return sorted(list(tissues))
        except Exception as e:
            print(f"Error fetching tissues: {e}")
            return []

    def get_available_cell_types(
        self,
        organism: str = "Homo sapiens",
        tissue: Optional[str] = None,
    ) -> List[str]:
        """Get list of available cell types.

        Args:
            organism: Species name
            tissue: Optional tissue filter

        Returns:
            List of cell type names
        """
        try:
            census = self._get_census()
            obs = census["census_data"][organism].obs

            if tissue:
                filter_str = f"tissue == '{tissue}'"
                df = obs.read(column_names=["cell_type"], value_filter=filter_str).concat().to_pandas()
            else:
                df = obs.read(column_names=["cell_type"]).concat().to_pandas()

            return sorted(list(df["cell_type"].unique()))
        except Exception as e:
            print(f"Error fetching cell types: {e}")
            return []

    def search_datasets(
        self,
        organism: str = "Homo sapiens",
        tissue: Optional[List[str]] = None,
        cell_type: Optional[List[str]] = None,
        disease: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[DatasetInfo]:
        """Search for datasets matching criteria.

        Args:
            organism: Species
            tissue: List of tissues
            cell_type: List of cell types
            disease: List of diseases
            limit: Maximum results

        Returns:
            List of matching datasets
        """
        # Build filter string
        filters = []

        if tissue:
            tissue_filter = " or ".join([f"tissue == '{t}'" for t in tissue])
            filters.append(f"({tissue_filter})")

        if cell_type:
            ct_filter = " or ".join([f"cell_type == '{c}'" for c in cell_type])
            filters.append(f"({ct_filter})")

        if disease:
            disease_filter = " or ".join([f"disease == '{d}'" for d in disease])
            filters.append(f"({disease_filter})")

        filter_str = " and ".join(filters) if filters else None

        try:
            census = self._get_census()
            obs = census["census_data"][organism].obs

            # Read metadata
            columns = ["dataset_id", "tissue", "cell_type", "assay", "disease"]
            if filter_str:
                df = obs.read(column_names=columns, value_filter=filter_str).concat().to_pandas()
            else:
                df = obs.read(column_names=columns).concat().to_pandas()

            # Aggregate by dataset
            datasets = []
            for dataset_id in df["dataset_id"].unique()[:limit]:
                subset = df[df["dataset_id"] == dataset_id]
                datasets.append(DatasetInfo(
                    dataset_id=dataset_id,
                    title=dataset_id,
                    description=f"Tissues: {', '.join(subset['tissue'].unique()[:3])}",
                    organism=organism,
                    tissue=", ".join(subset["tissue"].unique()[:3]),
                    cell_count=len(subset),
                    assay=subset["assay"].iloc[0] if len(subset) > 0 else "",
                ))

            return datasets

        except Exception as e:
            print(f"Error searching datasets: {e}")
            return []

    def fetch_data(
        self,
        organism: str = "Homo sapiens",
        obs_filter: Optional[str] = None,
        var_filter: Optional[str] = None,
        max_cells: int = 10000,
    ):
        """Fetch AnnData from Census.

        Args:
            organism: Species
            obs_filter: Cell filter string
            var_filter: Gene filter string
            max_cells: Maximum cells to fetch

        Returns:
            AnnData object
        """
        try:
            import cellxgene_census

            with cellxgene_census.open_soma(census_version=self.census_version) as census:
                adata = cellxgene_census.get_anndata(
                    census=census,
                    organism=organism,
                    obs_value_filter=obs_filter,
                    var_value_filter=var_filter,
                )

                # Subsample if too large
                if adata.n_obs > max_cells:
                    import numpy as np
                    idx = np.random.choice(adata.n_obs, max_cells, replace=False)
                    adata = adata[idx, :].copy()

                return adata

        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

    def close(self):
        """Close census connection."""
        if self._census is not None:
            self._census.close()
            self._census = None
