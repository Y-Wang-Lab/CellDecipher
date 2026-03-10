"""UCSC Genome Browser service for fetching gene sequences."""

import requests
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import re


@dataclass
class GeneInfo:
    """Gene information from UCSC."""
    gene_name: str
    ensembl_id: Optional[str]
    chrom: str
    start: int
    end: int
    strand: str
    transcript_id: str
    exon_starts: List[int]
    exon_ends: List[int]
    cds_start: Optional[int] = None
    cds_end: Optional[int] = None
    sequence: Optional[str] = None


class UCSCService:
    """Service for fetching sequences from UCSC Genome Browser."""

    # Genome assembly mappings
    ASSEMBLIES = {
        "human": "hg38",
        "mouse": "mm39",
        "mouse_mm10": "mm10",
    }

    # API endpoints
    BASE_URL = "https://api.genome.ucsc.edu"

    def __init__(self):
        self.session = requests.Session()

    def search_gene(
        self,
        query: str,
        species: str = "human",
        limit: int = 10,
    ) -> List[Dict]:
        """Search for genes by name or ENSEMBL ID.

        Args:
            query: Gene name or ENSEMBL ID
            species: 'human' or 'mouse'
            limit: Maximum results to return

        Returns:
            List of matching genes with coordinates
        """
        genome = self.ASSEMBLIES.get(species, "hg38")

        # Use UCSC search endpoint
        url = f"{self.BASE_URL}/search"
        params = {
            "genome": genome,
            "search": query,
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = []
            if "positionMatches" in data:
                for match in data["positionMatches"][:limit]:
                    if "matches" in match:
                        for m in match["matches"]:
                            results.append({
                                "gene_name": m.get("itemName", query),
                                "position": m.get("position", ""),
                                "description": m.get("description", ""),
                            })
            return results
        except Exception as e:
            print(f"Error searching gene: {e}")
            return []

    def get_gene_info_from_refgene(
        self,
        gene_name: str,
        species: str = "human",
    ) -> Optional[GeneInfo]:
        """Get gene information including exon coordinates from refGene track.

        Args:
            gene_name: Gene symbol
            species: 'human' or 'mouse'

        Returns:
            GeneInfo with exon coordinates or None
        """
        genome = self.ASSEMBLIES.get(species, "hg38")

        # Query refGene track for gene info
        url = f"{self.BASE_URL}/getData/track"
        params = {
            "genome": genome,
            "track": "refGene",
            "name": gene_name,
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Check if we got results
            if "refGene" not in data or not data["refGene"]:
                # Try ncbiRefSeq as fallback
                params["track"] = "ncbiRefSeq"
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if "ncbiRefSeq" not in data or not data["ncbiRefSeq"]:
                    return None
                track_data = data["ncbiRefSeq"]
            else:
                track_data = data["refGene"]

            # Get first transcript (usually the canonical one)
            if isinstance(track_data, list):
                gene_data = track_data[0]
            else:
                gene_data = track_data

            # Parse exon coordinates
            exon_starts = []
            exon_ends = []

            if "exonStarts" in gene_data and "exonEnds" in gene_data:
                # Parse comma-separated values
                starts_str = gene_data["exonStarts"]
                ends_str = gene_data["exonEnds"]

                if isinstance(starts_str, str):
                    exon_starts = [int(x) for x in starts_str.strip(",").split(",") if x]
                    exon_ends = [int(x) for x in ends_str.strip(",").split(",") if x]
                elif isinstance(starts_str, list):
                    exon_starts = starts_str
                    exon_ends = ends_str

            return GeneInfo(
                gene_name=gene_data.get("name2", gene_name),
                ensembl_id=gene_data.get("name"),
                chrom=gene_data.get("chrom", ""),
                start=gene_data.get("txStart", 0),
                end=gene_data.get("txEnd", 0),
                strand=gene_data.get("strand", "+"),
                transcript_id=gene_data.get("name", ""),
                exon_starts=exon_starts,
                exon_ends=exon_ends,
                cds_start=gene_data.get("cdsStart"),
                cds_end=gene_data.get("cdsEnd"),
            )

        except Exception as e:
            print(f"Error getting gene info: {e}")
            return None

    def get_sequence(
        self,
        chrom: str,
        start: int,
        end: int,
        species: str = "human",
    ) -> Optional[str]:
        """Get DNA sequence for genomic region.

        Args:
            chrom: Chromosome (e.g., 'chr1')
            start: Start position (0-based)
            end: End position
            species: 'human' or 'mouse'

        Returns:
            DNA sequence string or None
        """
        genome = self.ASSEMBLIES.get(species, "hg38")

        url = f"{self.BASE_URL}/getData/sequence"
        params = {
            "genome": genome,
            "chrom": chrom,
            "start": start,
            "end": end,
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if "dna" in data:
                return data["dna"].upper()
            return None
        except Exception as e:
            print(f"Error fetching sequence: {e}")
            return None

    def reverse_complement(self, sequence: str) -> str:
        """Get reverse complement of DNA sequence.

        Args:
            sequence: DNA sequence

        Returns:
            Reverse complement sequence
        """
        complement = {"A": "T", "T": "A", "G": "C", "C": "G", "N": "N"}
        return "".join(complement.get(base, "N") for base in reversed(sequence.upper()))

    def get_exon_sequence(
        self,
        gene_name: str,
        species: str = "human",
        sequence_type: str = "mRNA",
    ) -> Optional[Tuple[str, str, GeneInfo]]:
        """Get exon-only sequence (mRNA) for a gene.

        Args:
            gene_name: Gene symbol
            species: 'human' or 'mouse'
            sequence_type: 'mRNA' (all exons) or 'CDS' (coding region only)

        Returns:
            Tuple of (sequence, transcript_id, gene_info) or None
        """
        # Get gene info with exon coordinates
        gene_info = self.get_gene_info_from_refgene(gene_name, species)

        if not gene_info:
            print(f"Could not find gene info for {gene_name}")
            return None

        if not gene_info.exon_starts or not gene_info.exon_ends:
            print(f"No exon coordinates found for {gene_name}")
            return None

        # Fetch each exon sequence and concatenate
        exon_sequences = []

        for i, (start, end) in enumerate(zip(gene_info.exon_starts, gene_info.exon_ends)):
            # For CDS, trim to coding region
            if sequence_type == "CDS" and gene_info.cds_start and gene_info.cds_end:
                # Skip exons entirely outside CDS
                if end <= gene_info.cds_start or start >= gene_info.cds_end:
                    continue

                # Trim exon to CDS boundaries
                exon_start = max(start, gene_info.cds_start)
                exon_end = min(end, gene_info.cds_end)
            else:
                exon_start = start
                exon_end = end

            # Fetch exon sequence
            seq = self.get_sequence(gene_info.chrom, exon_start, exon_end, species)
            if seq:
                exon_sequences.append(seq)

        if not exon_sequences:
            print(f"Could not fetch exon sequences for {gene_name}")
            return None

        # Concatenate exons
        mrna_sequence = "".join(exon_sequences)

        # If on minus strand, reverse complement
        if gene_info.strand == "-":
            mrna_sequence = self.reverse_complement(mrna_sequence)
            # Also reverse the order of exons for minus strand genes
            # (exons are stored 5' to 3' genomically, need to reverse for transcript)

        gene_info.sequence = mrna_sequence

        return (mrna_sequence, gene_info.transcript_id, gene_info)

    def fetch_sequence_for_probe_design(
        self,
        gene_identifier: str,
        species: str = "human",
        sequence_type: str = "mRNA",
    ) -> Optional[Dict]:
        """Fetch exon sequence suitable for probe design.

        Args:
            gene_identifier: Gene name or ENSEMBL ID
            species: 'human' or 'mouse'
            sequence_type: 'mRNA' or 'CDS'

        Returns:
            Dict with gene info and sequence, or None
        """
        result = self.get_exon_sequence(gene_identifier, species, sequence_type)

        if result:
            sequence, transcript_id, gene_info = result
            return {
                "gene_name": gene_info.gene_name,
                "transcript_id": transcript_id,
                "sequence": sequence,
                "length": len(sequence),
                "species": species,
                "sequence_type": sequence_type,
                "n_exons": len(gene_info.exon_starts),
                "strand": gene_info.strand,
                "chrom": gene_info.chrom,
            }
        return None

    def batch_fetch_sequences(
        self,
        gene_list: List[str],
        species: str = "human",
        sequence_type: str = "mRNA",
    ) -> Dict[str, Optional[Dict]]:
        """Fetch exon sequences for multiple genes.

        Args:
            gene_list: List of gene names or ENSEMBL IDs
            species: 'human' or 'mouse'
            sequence_type: 'mRNA' or 'CDS'

        Returns:
            Dict mapping gene names to sequence info
        """
        results = {}
        for gene in gene_list:
            results[gene] = self.fetch_sequence_for_probe_design(gene, species, sequence_type)
        return results
