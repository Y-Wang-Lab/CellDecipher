"""Query models for data source searches."""

from typing import Optional, List
from pydantic import BaseModel, Field


class CellxGeneQuery(BaseModel):
    """Query parameters for CELLxGENE Census search."""

    organism: str = Field(default="Homo sapiens", description="Species name")
    tissue: Optional[List[str]] = Field(default=None, description="List of tissues")
    cell_type: Optional[List[str]] = Field(default=None, description="List of cell types")
    disease: Optional[List[str]] = Field(default=None, description="List of diseases")
    assay: Optional[List[str]] = Field(default=None, description="Sequencing assays")
    sex: Optional[str] = Field(default=None, description="Biological sex")
    development_stage: Optional[str] = Field(default=None, description="Development stage")

    def to_filter_string(self) -> str:
        """Convert to CELLxGENE filter string."""
        filters = []

        if self.tissue:
            tissue_filter = " or ".join([f"tissue == '{t}'" for t in self.tissue])
            filters.append(f"({tissue_filter})")

        if self.cell_type:
            ct_filter = " or ".join([f"cell_type == '{c}'" for c in self.cell_type])
            filters.append(f"({ct_filter})")

        if self.disease:
            disease_filter = " or ".join([f"disease == '{d}'" for d in self.disease])
            filters.append(f"({disease_filter})")

        if self.sex:
            filters.append(f"sex == '{self.sex}'")

        return " and ".join(filters) if filters else ""


class GEOQuery(BaseModel):
    """Query parameters for GEO search."""

    keywords: str = Field(description="Search keywords")
    organism: Optional[str] = Field(default=None, description="Organism filter")
    platform: Optional[str] = Field(default=None, description="Platform filter")
    study_type: Optional[str] = Field(default=None, description="Study type")
