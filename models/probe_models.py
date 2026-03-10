"""Probe design data models."""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class ProbeDesignRequest(BaseModel):
    """Request parameters for probe design."""

    gene_name: str = Field(description="Gene name or ENSEMBL ID")
    sequence: str = Field(description="Target sequence")
    species: str = Field(default="mouse", description="Species for genome masking")
    mode: str = Field(default="HCR3.0", description="Probe mode: HCR3.0 or BarFISH")
    channel: str = Field(default="B1", description="Channel or barcode name")

    # Design parameters
    max_probes: int = Field(default=20, ge=1, le=100)
    min_gc: float = Field(default=38.0, ge=20, le=50)
    max_gc: float = Field(default=62.0, ge=50, le=80)
    min_gibbs: float = Field(default=-70.0)
    max_gibbs: float = Field(default=-50.0)
    num_overlap: int = Field(default=10, ge=0, le=52)

    # Filtering options
    genomemask: bool = Field(default=True)
    repeatmask: bool = Field(default=False)


class ProbeSequence(BaseModel):
    """Individual probe sequence."""

    name: str
    sequence: str
    start: int
    p1: str = Field(alias="P1")
    p2: str = Field(alias="P2")
    channel: str
    gc_percent: float = Field(alias="GC")
    gibbs: float = Field(alias="Gibbs")

    class Config:
        populate_by_name = True


class ProbeResult(BaseModel):
    """Result from probe design."""

    gene_name: str
    channel: str
    probes: List[Dict]
    total_probes: int
    estimated_cost: float
    success: bool
    error_message: Optional[str] = None
