"""Probe design service integrating HCRProbeDesign package."""

import sys
import os
import tempfile
import pandas as pd
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path

# Add bundled probe_design_lib to path
PROBE_DESIGN_PATH = str(Path(__file__).parent.parent / "probe_design_lib")
if PROBE_DESIGN_PATH not in sys.path:
    sys.path.insert(0, PROBE_DESIGN_PATH)


@dataclass
class ProbeResult:
    """Result from probe design."""
    gene_name: str
    channel: str
    probes: List[Dict]
    total_probes: int
    estimated_cost: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class ProbeDesignParams:
    """Parameters for probe design."""
    species: str = "mouse"
    channel: str = "B1"
    max_probes: int = 20
    min_gc: float = 38.0
    max_gc: float = 62.0
    min_gibbs: float = -70.0
    max_gibbs: float = -50.0
    num_overlap: int = 10
    genomemask: bool = True
    repeatmask: bool = False


class ProbeDesignService:
    """Service for designing HCR3.0 and BarFISH probes."""

    # HCR3.0 channels
    HCR_CHANNELS = ["B1", "B2", "B3", "B4", "B5", "BC_1", "BC_2"]

    def __init__(self, barcode_csv_path: Optional[str] = None):
        """Initialize probe design service.

        Args:
            barcode_csv_path: Path to barcode CSV file for BarFISH
        """
        default_barcode_path = str(Path(__file__).parent.parent / "data" / "bc30mer_filtered_v2.csv")
        self.barcode_csv_path = barcode_csv_path or default_barcode_path
        self._barcodes_df = None
        self._hcr_probedesign = None
        self._barfish_probedesign = None

    def _load_modules(self):
        """Lazy load probe design modules."""
        if self._hcr_probedesign is None:
            try:
                import probeDesign
                import probeDesign_batch
                self._hcr_probedesign = probeDesign
                self._barfish_probedesign = probeDesign_batch
            except ImportError as e:
                raise ImportError(f"Failed to import probe design modules: {e}")

    @property
    def barcodes_df(self) -> pd.DataFrame:
        """Load barcode DataFrame lazily."""
        if self._barcodes_df is None:
            if os.path.exists(self.barcode_csv_path):
                self._barcodes_df = pd.read_csv(self.barcode_csv_path, index_col=0)
            else:
                raise FileNotFoundError(f"Barcode CSV not found: {self.barcode_csv_path}")
        return self._barcodes_df

    def get_hcr_channels(self) -> List[str]:
        """Get available HCR3.0 channels."""
        return self.HCR_CHANNELS

    def get_barcode_list(self, limit: int = 100) -> List[str]:
        """Get list of available barcodes for BarFISH.

        Args:
            limit: Maximum number to return (for UI performance)

        Returns:
            List of barcode names
        """
        return list(self.barcodes_df.index[:limit])

    def search_barcodes(self, query: str, limit: int = 50) -> List[str]:
        """Search barcodes by name.

        Args:
            query: Search string
            limit: Maximum results

        Returns:
            List of matching barcode names
        """
        all_barcodes = list(self.barcodes_df.index)
        matches = [b for b in all_barcodes if query.lower() in b.lower()]
        return matches[:limit]

    def get_barcode_info(self, barcode_name: str) -> Optional[Dict]:
        """Get information about a specific barcode.

        Args:
            barcode_name: Name of the barcode

        Returns:
            Dict with barcode properties
        """
        if barcode_name in self.barcodes_df.index:
            row = self.barcodes_df.loc[barcode_name]
            return row.to_dict()
        return None

    def design_hcr_probes(
        self,
        fasta_path: str,
        gene_name: str,
        channel: str = "B1",
        params: Optional[ProbeDesignParams] = None,
    ) -> ProbeResult:
        """Design HCR3.0 probes for a gene.

        Args:
            fasta_path: Path to FASTA file with target sequence
            gene_name: Name of the gene
            channel: HCR channel (B1-B5, BC_1, BC_2)
            params: Design parameters

        Returns:
            ProbeResult with designed probes
        """
        self._load_modules()

        if params is None:
            params = ProbeDesignParams()

        # Run in a temporary directory to contain intermediate files (.sam, _reads.fa)
        # created by HCRProbeDesign's genomeMask.py
        original_dir = os.getcwd()

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)

                # Create temp output files
                output_path = os.path.join(temp_dir, 'output.csv')
                idt_output_path = os.path.join(temp_dir, 'idt_output.csv')

                # Run probe design
                best_tiles = self._hcr_probedesign.probe_design(
                    file_path=fasta_path,
                    output=output_path,
                    idt_output=idt_output_path,
                    targetName=gene_name,
                    species=params.species,
                    channel=channel,
                    maxProbes=params.max_probes,
                    minGC=params.min_gc,
                    maxGC=params.max_gc,
                    minGibbs=params.min_gibbs,
                    maxGibbs=params.max_gibbs,
                    numOverlap=params.num_overlap,
                    genomemask=params.genomemask,
                    repeatmask=params.repeatmask,
                )

                # Parse results
                probes = []
                for tile in best_tiles:
                    probes.append({
                        "name": tile.name,
                        "sequence": tile.sequence,
                        "start": tile.start,
                        "P1": tile.P1,
                        "P2": tile.P2,
                        "channel": tile.channel,
                        "GC": tile.GC(),
                        "Gibbs": tile.Gibbs,
                    })

                # Calculate cost
                cost = self._calculate_cost(probes)

                return ProbeResult(
                    gene_name=gene_name,
                    channel=channel,
                    probes=probes,
                    total_probes=len(probes),
                    estimated_cost=cost,
                    success=True,
                )

            except Exception as e:
                return ProbeResult(
                    gene_name=gene_name,
                    channel=channel,
                    probes=[],
                    total_probes=0,
                    estimated_cost=0,
                    success=False,
                    error_message=str(e),
                )

            finally:
                os.chdir(original_dir)

    def design_barfish_probes(
        self,
        fasta_path: str,
        gene_name: str,
        barcode_name: str,
        params: Optional[ProbeDesignParams] = None,
    ) -> ProbeResult:
        """Design BarFISH probes for a gene.

        Args:
            fasta_path: Path to FASTA file with target sequence
            gene_name: Name of the gene
            barcode_name: Name of the barcode from the library
            params: Design parameters

        Returns:
            ProbeResult with designed probes
        """
        self._load_modules()

        if params is None:
            params = ProbeDesignParams()

        # Get barcode info
        barcode_info = self.barcodes_df.loc[barcode_name]

        # Run in a temporary directory to contain intermediate files (.sam, _reads.fa)
        # created by HCRProbeDesign's genomeMask.py
        original_dir = os.getcwd()

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)

                # Create temp output files
                output_path = os.path.join(temp_dir, 'output.csv')
                idt_output_path = os.path.join(temp_dir, 'idt_output.csv')

                # Prepare sequence dict
                import sequencelib
                with open(fasta_path, 'r') as f:
                    fasta_iter = sequencelib.FastaIterator(f)
                    seq = next(fasta_iter)
                    seq['name'] = gene_name

                # Run BarFISH probe design
                best_tiles, num_probes = self._barfish_probedesign.probe_design(
                    mySeq=seq,
                    output=output_path,
                    idt_output=idt_output_path,
                    targetName=gene_name,
                    species=params.species,
                    channel=barcode_info,
                    maxProbes=params.max_probes,
                    minGC=params.min_gc,
                    maxGC=params.max_gc,
                    minGibbs=params.min_gibbs,
                    maxGibbs=params.max_gibbs,
                    numOverlap=params.num_overlap,
                    genomemask=params.genomemask,
                    repeatmask=params.repeatmask,
                    tileStep=10,
                )

                # Parse results
                probes = []
                for tile in best_tiles:
                    probes.append({
                        "name": tile.name,
                        "sequence": tile.sequence,
                        "start": tile.start,
                        "P1": tile.P1,
                        "P2": tile.P2,
                        "channel": barcode_name,
                        "GC": tile.GC(),
                        "Gibbs": tile.Gibbs,
                    })

                # Calculate cost
                cost = self._calculate_cost(probes)

                return ProbeResult(
                    gene_name=gene_name,
                    channel=barcode_name,
                    probes=probes,
                    total_probes=len(probes),
                    estimated_cost=cost,
                    success=True,
                )

            except Exception as e:
                return ProbeResult(
                    gene_name=gene_name,
                    channel=barcode_name,
                    probes=[],
                    total_probes=0,
                    estimated_cost=0,
                    success=False,
                    error_message=str(e),
                )

            finally:
                os.chdir(original_dir)

    def _calculate_cost(self, probes: List[Dict], price_per_base: float = 0.11) -> float:
        """Calculate estimated synthesis cost.

        Args:
            probes: List of probe dicts with P1/P2 sequences
            price_per_base: Price per base pair

        Returns:
            Estimated cost in dollars
        """
        total = 0.0
        for probe in probes:
            p1_len = len(probe.get("P1", ""))
            p2_len = len(probe.get("P2", ""))
            total += (p1_len + p2_len) * price_per_base
        return round(total, 2)

    def format_idt_output(self, probes: List[Dict]) -> pd.DataFrame:
        """Format probes for IDT ordering.

        Args:
            probes: List of probe dicts

        Returns:
            DataFrame formatted for IDT plate ordering
        """
        rows = []
        for probe in probes:
            # Add odd probe (P1)
            rows.append({
                "Name": f"{probe['name']}:{probe['channel']}:odd",
                "Sequence": probe["P1"],
            })
            # Add even probe (P2)
            rows.append({
                "Name": f"{probe['name']}:{probe['channel']}:even",
                "Sequence": probe["P2"],
            })

        return pd.DataFrame(rows)

    def format_summary_table(self, probes: List[Dict]) -> pd.DataFrame:
        """Format probes as summary table.

        Args:
            probes: List of probe dicts

        Returns:
            DataFrame with probe summary
        """
        return pd.DataFrame([{
            "Name": p["name"],
            "Start": p["start"],
            "Sequence": p["sequence"],
            "P1": p["P1"],
            "P2": p["P2"],
            "Channel": p["channel"],
            "GC%": f"{p['GC']:.1f}",
            "Gibbs": f"{p['Gibbs']:.1f}",
        } for p in probes])
