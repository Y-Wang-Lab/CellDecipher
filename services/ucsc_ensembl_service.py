"""UCSC Genome Browser and Ensembl service for fetching gene sequences."""

import requests
import time
from typing import Optional, Dict, List
from dataclasses import dataclass


@dataclass
class TranscriptInfo:
    """Transcript information."""
    gene_name: str
    transcript_id: str
    species: str
    description: str
    source: str  # 'UCSC' or 'Ensembl'


class UCSCEnsemblService:
    """Service for fetching sequences from UCSC Genome Browser and Ensembl."""

    # UCSC API endpoints
    UCSC_API_BASE = "https://api.genome.ucsc.edu"

    # Ensembl REST API
    ENSEMBL_BASE = "https://rest.ensembl.org"

    # Genome assemblies
    UCSC_ASSEMBLIES = {
        "human": "hg38",
        "mouse": "mm39",
    }

    ENSEMBL_SPECIES = {
        "human": "homo_sapiens",
        "mouse": "mus_musculus",
    }

    def __init__(self):
        """Initialize the service."""
        self.session = requests.Session()
        self._last_request_time = 0

    def _rate_limit(self, min_interval: float = 0.2):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _make_request(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        retries: int = 3
    ) -> Optional[requests.Response]:
        """Make a rate-limited request with retries."""
        for attempt in range(retries):
            self._rate_limit()
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:
                    wait_time = (attempt + 1) * 2
                    print(f"Rate limited, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                print(f"Request error: {e}")
                return None
            except Exception as e:
                print(f"Request error: {e}")
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None
        return None

    # =========================================================================
    # UCSC Genome Browser Methods
    # =========================================================================

    def ucsc_search_gene(
        self,
        gene_name: str,
        species: str = "mouse",
    ) -> Optional[Dict]:
        """Search for a gene in UCSC and get RefSeq transcript info.

        Args:
            gene_name: Gene symbol (e.g., "Gad1", "Snap25")
            species: 'human' or 'mouse'

        Returns:
            Dict with transcript info or None
        """
        assembly = self.UCSC_ASSEMBLIES.get(species, "mm39")

        # Use UCSC API to search for gene in refGene track
        url = f"{self.UCSC_API_BASE}/search"
        params = {
            "genome": assembly,
            "search": gene_name,
        }

        response = self._make_request(url, params=params)
        if not response:
            return None

        data = response.json()

        # Look for matches in the search results
        if "positionMatches" in data:
            for match in data.get("positionMatches", []):
                if match.get("genome") == assembly:
                    matches = match.get("matches", [])
                    for m in matches:
                        # Look for refGene matches
                        if "refGene" in m.get("tableName", "") or "ncbiRefSeq" in m.get("tableName", ""):
                            return {
                                "gene_name": gene_name,
                                "position": m.get("position", ""),
                                "description": m.get("posName", ""),
                                "assembly": assembly,
                            }

        return None

    def ucsc_get_refseq_transcripts(
        self,
        gene_name: str,
        species: str = "mouse",
    ) -> List[str]:
        """Get RefSeq transcript IDs for a gene from UCSC.

        Args:
            gene_name: Gene symbol
            species: 'human' or 'mouse'

        Returns:
            List of RefSeq accessions (NM_*)
        """
        assembly = self.UCSC_ASSEMBLIES.get(species, "mm39")

        # Query the ncbiRefSeq track via API
        url = f"{self.UCSC_API_BASE}/getData/track"
        params = {
            "genome": assembly,
            "track": "ncbiRefSeq",
            "maxItemsOutput": 100,
        }

        # First get gene position
        gene_info = self.ucsc_search_gene(gene_name, species)
        if gene_info and gene_info.get("position"):
            params["chrom"] = gene_info["position"].split(":")[0] if ":" in gene_info["position"] else None

        response = self._make_request(url, params=params)
        if not response:
            return []

        try:
            data = response.json()
            transcripts = []

            # Parse the track data
            if "ncbiRefSeq" in data:
                for item in data["ncbiRefSeq"]:
                    name = item.get("name", "")
                    gene = item.get("name2", "")
                    # Match gene name (case-insensitive)
                    if gene.lower() == gene_name.lower() and name.startswith("NM_"):
                        transcripts.append(name)

            return list(set(transcripts))  # Remove duplicates
        except Exception as e:
            print(f"Error parsing UCSC response: {e}")
            return []

    def ucsc_fetch_sequence(
        self,
        gene_name: str,
        species: str = "mouse",
    ) -> Optional[Dict]:
        """Fetch mRNA sequence from UCSC Genome Browser.

        Uses the UCSC DAS server to get sequences.

        Args:
            gene_name: Gene symbol or RefSeq accession
            species: 'human' or 'mouse'

        Returns:
            Dict with sequence info or None
        """
        assembly = self.UCSC_ASSEMBLIES.get(species, "mm39")

        # Check if input is already a RefSeq accession
        if gene_name.startswith(("NM_", "XM_", "NR_")):
            accession = gene_name
            original_gene_name = gene_name
        else:
            # Search for transcripts
            transcripts = self.ucsc_get_refseq_transcripts(gene_name, species)
            if not transcripts:
                print(f"No RefSeq transcripts found for {gene_name} in UCSC")
                return None
            accession = transcripts[0]  # Use first NM_ transcript
            original_gene_name = gene_name

        # Use UCSC Table Browser API to get sequence
        # Alternative: use the getData/sequence endpoint
        url = f"{self.UCSC_API_BASE}/getData/sequence"

        # First we need to get the genomic coordinates for this transcript
        track_url = f"{self.UCSC_API_BASE}/getData/track"
        params = {
            "genome": assembly,
            "track": "ncbiRefSeq",
            "maxItemsOutput": 500,
        }

        response = self._make_request(track_url, params=params)
        if not response:
            return None

        try:
            data = response.json()
            transcript_info = None

            # Find the specific transcript
            if "ncbiRefSeq" in data:
                for item in data["ncbiRefSeq"]:
                    if item.get("name", "") == accession:
                        transcript_info = item
                        break
                    # Also check gene name match
                    if item.get("name2", "").lower() == gene_name.lower() and item.get("name", "").startswith("NM_"):
                        if transcript_info is None:
                            transcript_info = item
                            accession = item.get("name", "")

            if not transcript_info:
                print(f"Could not find transcript info for {accession}")
                return None

            # Get sequence using coordinates
            chrom = transcript_info.get("chrom", "")
            start = transcript_info.get("txStart", 0)
            end = transcript_info.get("txEnd", 0)
            strand = transcript_info.get("strand", "+")
            exon_starts = transcript_info.get("exonStarts", [])
            exon_ends = transcript_info.get("exonEnds", [])

            # Fetch exon sequences and concatenate for mRNA
            sequence_parts = []

            # Parse exon coordinates
            if isinstance(exon_starts, str):
                exon_starts = [int(x) for x in exon_starts.split(",") if x]
            if isinstance(exon_ends, str):
                exon_ends = [int(x) for x in exon_ends.split(",") if x]

            for ex_start, ex_end in zip(exon_starts, exon_ends):
                seq_url = f"{self.UCSC_API_BASE}/getData/sequence"
                seq_params = {
                    "genome": assembly,
                    "chrom": chrom,
                    "start": ex_start,
                    "end": ex_end,
                }

                seq_response = self._make_request(seq_url, params=seq_params)
                if seq_response:
                    seq_data = seq_response.json()
                    dna = seq_data.get("dna", "")
                    sequence_parts.append(dna)

            # Concatenate exons
            full_sequence = "".join(sequence_parts).upper()

            # Reverse complement if on minus strand
            if strand == "-":
                full_sequence = self._reverse_complement(full_sequence)

            if not full_sequence:
                return None

            return {
                "gene_name": original_gene_name,
                "transcript_id": accession,
                "sequence": full_sequence,
                "length": len(full_sequence),
                "species": species,
                "sequence_type": "mRNA",
                "source": "UCSC",
                "assembly": assembly,
            }

        except Exception as e:
            print(f"Error fetching UCSC sequence: {e}")
            return None

    # =========================================================================
    # Ensembl Methods
    # =========================================================================

    def ensembl_search_gene(
        self,
        gene_name: str,
        species: str = "mouse",
    ) -> Optional[Dict]:
        """Search for a gene in Ensembl.

        Args:
            gene_name: Gene symbol (e.g., "Gad1", "Snap25")
            species: 'human' or 'mouse'

        Returns:
            Dict with gene info or None
        """
        ensembl_species = self.ENSEMBL_SPECIES.get(species, "mus_musculus")

        # Use Ensembl lookup endpoint
        url = f"{self.ENSEMBL_BASE}/lookup/symbol/{ensembl_species}/{gene_name}"
        headers = {"Content-Type": "application/json"}

        response = self._make_request(url, headers=headers)
        if not response:
            return None

        try:
            data = response.json()
            return {
                "gene_id": data.get("id", ""),
                "gene_name": data.get("display_name", gene_name),
                "description": data.get("description", ""),
                "biotype": data.get("biotype", ""),
                "species": species,
            }
        except Exception as e:
            print(f"Error parsing Ensembl response: {e}")
            return None

    def ensembl_get_transcripts(
        self,
        gene_name: str,
        species: str = "mouse",
    ) -> List[Dict]:
        """Get all transcripts for a gene from Ensembl.

        Args:
            gene_name: Gene symbol
            species: 'human' or 'mouse'

        Returns:
            List of transcript info dicts
        """
        # First get gene ID
        gene_info = self.ensembl_search_gene(gene_name, species)
        if not gene_info:
            return []

        gene_id = gene_info.get("gene_id", "")
        if not gene_id:
            return []

        ensembl_species = self.ENSEMBL_SPECIES.get(species, "mus_musculus")

        # Get transcripts for the gene
        url = f"{self.ENSEMBL_BASE}/lookup/id/{gene_id}"
        headers = {"Content-Type": "application/json"}
        params = {"expand": 1}  # Include transcripts

        response = self._make_request(url, params=params, headers=headers)
        if not response:
            return []

        try:
            data = response.json()
            transcripts = []

            for transcript in data.get("Transcript", []):
                transcripts.append({
                    "transcript_id": transcript.get("id", ""),
                    "display_name": transcript.get("display_name", ""),
                    "biotype": transcript.get("biotype", ""),
                    "is_canonical": transcript.get("is_canonical", 0),
                    "length": transcript.get("length", 0),
                })

            # Sort by canonical status and length
            transcripts.sort(key=lambda x: (-x.get("is_canonical", 0), -x.get("length", 0)))

            return transcripts
        except Exception as e:
            print(f"Error getting Ensembl transcripts: {e}")
            return []

    def ensembl_fetch_sequence(
        self,
        gene_name: str,
        species: str = "mouse",
        transcript_id: Optional[str] = None,
        sequence_type: str = "mRNA",
    ) -> Optional[Dict]:
        """Fetch sequence from Ensembl.

        Args:
            gene_name: Gene symbol or Ensembl transcript ID (ENSMUST*)
            species: 'human' or 'mouse'
            transcript_id: Optional specific transcript ID
            sequence_type: 'mRNA' (cdna), 'CDS' (coding), or 'genomic' (unspliced)

        Returns:
            Dict with sequence info or None
        """
        # Check if input is already an Ensembl transcript ID
        if gene_name.startswith(("ENSMUST", "ENST")):
            transcript_id = gene_name
            original_gene_name = gene_name
        else:
            original_gene_name = gene_name

            # Get transcripts and pick the canonical one
            if not transcript_id:
                transcripts = self.ensembl_get_transcripts(gene_name, species)
                if not transcripts:
                    print(f"No Ensembl transcripts found for {gene_name}")
                    return None
                transcript_id = transcripts[0]["transcript_id"]  # Use canonical/longest

        # Map sequence_type to Ensembl API type parameter
        type_mapping = {
            "mRNA": "cdna",      # Spliced transcript (exons only)
            "CDS": "cds",        # Coding sequence only
            "genomic": "genomic", # Unspliced with introns
        }
        ensembl_type = type_mapping.get(sequence_type, "cdna")

        # Fetch sequence
        url = f"{self.ENSEMBL_BASE}/sequence/id/{transcript_id}"
        headers = {"Content-Type": "text/plain"}
        params = {"type": ensembl_type}

        response = self._make_request(url, params=params, headers=headers)
        if not response:
            return None

        sequence = response.text.strip().upper()

        if not sequence:
            return None

        return {
            "gene_name": original_gene_name,
            "transcript_id": transcript_id,
            "sequence": sequence,
            "length": len(sequence),
            "species": species,
            "sequence_type": sequence_type,
            "source": "Ensembl",
        }

    # =========================================================================
    # Unified Interface
    # =========================================================================

    def fetch_sequence_for_probe_design(
        self,
        gene_identifier: str,
        species: str = "mouse",
        source: str = "Ensembl",
        sequence_type: str = "mRNA",
    ) -> Optional[Dict]:
        """Fetch sequence suitable for probe design.

        Args:
            gene_identifier: Gene name or Ensembl ID
            species: 'human' or 'mouse'
            source: 'Ensembl' (UCSC removed)
            sequence_type: 'mRNA', 'CDS', or 'genomic'

        Returns:
            Dict with gene info and sequence, or None
        """
        # Auto-detect source based on identifier format
        if gene_identifier.startswith(("ENSMUST", "ENST")):
            source = "Ensembl"

        if source == "Ensembl":
            return self.ensembl_fetch_sequence(gene_identifier, species, sequence_type=sequence_type)
        else:
            print(f"Unknown source: {source}")
            return None

    def batch_fetch_sequences(
        self,
        gene_list: List[str],
        species: str = "mouse",
        source: str = "Ensembl",
        sequence_type: str = "mRNA",
    ) -> Dict[str, Optional[Dict]]:
        """Fetch sequences for multiple genes.

        Args:
            gene_list: List of gene names or IDs
            species: 'human' or 'mouse'
            source: 'Ensembl'
            sequence_type: 'mRNA', 'CDS', or 'genomic'

        Returns:
            Dict mapping gene names to sequence info
        """
        results = {}
        for gene in gene_list:
            results[gene] = self.fetch_sequence_for_probe_design(gene, species, source, sequence_type)
        return results

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def _reverse_complement(self, sequence: str) -> str:
        """Get reverse complement of DNA sequence."""
        complement = {"A": "T", "T": "A", "G": "C", "C": "G", "N": "N"}
        return "".join(complement.get(base, "N") for base in reversed(sequence.upper()))
