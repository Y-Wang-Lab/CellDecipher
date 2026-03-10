"""NCBI Entrez service for fetching gene sequences."""

import requests
import time
import re
from typing import Optional, Dict, List
from dataclasses import dataclass
from xml.etree import ElementTree


@dataclass
class NCBIGeneInfo:
    """Gene information from NCBI."""
    gene_name: str
    gene_id: str
    species: str
    description: str
    mrna_accessions: List[str]
    chromosome: Optional[str] = None


class NCBIService:
    """Service for fetching sequences from NCBI Entrez."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Taxonomy IDs
    TAXIDS = {
        "human": "9606",
        "mouse": "10090",
    }

    def __init__(self, email: str = "user@example.com", api_key: Optional[str] = None):
        """Initialize NCBI service.

        Args:
            email: Email for NCBI API (required by NCBI)
            api_key: Optional NCBI API key for higher rate limits
        """
        self.email = email
        self.api_key = api_key
        self.session = requests.Session()
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting (3 requests/second without API key)."""
        # Be more conservative - 1 request per second without API key
        min_interval = 1.0 if not self.api_key else 0.11
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict, retries: int = 3) -> Optional[requests.Response]:
        """Make a rate-limited request to NCBI with retries."""
        params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        for attempt in range(retries):
            self._rate_limit()

            try:
                response = self.session.get(
                    f"{self.BASE_URL}/{endpoint}",
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:
                    # Rate limited - wait longer and retry
                    wait_time = (attempt + 1) * 2
                    print(f"Rate limited, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                print(f"NCBI request error: {e}")
                return None
            except Exception as e:
                print(f"NCBI request error: {e}")
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None

        return None

    def search_gene(
        self,
        gene_name: str,
        species: str = "human",
    ) -> Optional[NCBIGeneInfo]:
        """Search for a gene by name.

        Args:
            gene_name: Gene symbol (e.g., "SNAP25", "Snap25")
            species: 'human' or 'mouse'

        Returns:
            NCBIGeneInfo or None
        """
        taxid = self.TAXIDS.get(species, "9606")

        # Search gene database
        search_term = f"{gene_name}[Gene Name] AND {taxid}[Taxonomy ID]"

        response = self._make_request("esearch.fcgi", {
            "db": "gene",
            "term": search_term,
            "retmode": "json",
        })

        if not response:
            return None

        data = response.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            # Try broader search
            search_term = f"{gene_name} AND {taxid}[Taxonomy ID]"
            response = self._make_request("esearch.fcgi", {
                "db": "gene",
                "term": search_term,
                "retmode": "json",
            })
            if response:
                data = response.json()
                id_list = data.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return None

        gene_id = id_list[0]

        # Get gene summary
        response = self._make_request("esummary.fcgi", {
            "db": "gene",
            "id": gene_id,
            "retmode": "json",
        })

        if not response:
            return None

        data = response.json()
        result = data.get("result", {}).get(gene_id, {})

        return NCBIGeneInfo(
            gene_name=result.get("name", gene_name),
            gene_id=gene_id,
            species=species,
            description=result.get("description", ""),
            mrna_accessions=[],
            chromosome=result.get("chromosome"),
        )

    def get_refseq_mrna(
        self,
        gene_name: str,
        species: str = "human",
    ) -> Optional[str]:
        """Get RefSeq mRNA accession for a gene.

        Args:
            gene_name: Gene symbol
            species: 'human' or 'mouse'

        Returns:
            RefSeq mRNA accession (e.g., "NM_003081") or None
        """
        organism = "human" if species == "human" else "mouse"

        # Search nucleotide database for RefSeq mRNA
        # Use [Gene] field and organism, filter for RefSeq
        search_term = f"{gene_name}[Gene] AND {organism}[Organism] AND refseq[filter] AND biomol_mrna[PROP]"

        response = self._make_request("esearch.fcgi", {
            "db": "nucleotide",
            "term": search_term,
            "retmode": "json",
            "retmax": 10,
            "sort": "relevance",
        })

        if not response:
            return None

        data = response.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            # Try broader search without biomol filter
            search_term = f"{gene_name}[Gene] AND {organism}[Organism] AND refseq[filter]"
            response = self._make_request("esearch.fcgi", {
                "db": "nucleotide",
                "term": search_term,
                "retmode": "json",
                "retmax": 10,
            })
            if response:
                data = response.json()
                id_list = data.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return None

        # Get accessions and find NM_ (mRNA) accession preferentially
        response = self._make_request("esummary.fcgi", {
            "db": "nucleotide",
            "id": ",".join(id_list[:5]),
            "retmode": "json",
        })

        if not response:
            return None

        data = response.json()
        results = data.get("result", {})

        # Prefer NM_ accessions (curated mRNA) over XM_ (predicted)
        nm_accessions = []
        xm_accessions = []

        for uid in id_list[:5]:
            result = results.get(uid, {})
            accession = result.get("accessionversion", result.get("caption", ""))
            if accession.startswith("NM_"):
                nm_accessions.append(accession)
            elif accession.startswith("XM_"):
                xm_accessions.append(accession)

        # Return first NM_ if available, otherwise XM_
        if nm_accessions:
            return nm_accessions[0]
        elif xm_accessions:
            return xm_accessions[0]

        # Fallback to first result
        if id_list:
            result = results.get(id_list[0], {})
            return result.get("accessionversion", result.get("caption", ""))

    def fetch_sequence(
        self,
        accession: str,
    ) -> Optional[str]:
        """Fetch sequence by accession number.

        Args:
            accession: RefSeq accession (e.g., "NM_003081")

        Returns:
            Sequence string or None
        """
        response = self._make_request("efetch.fcgi", {
            "db": "nucleotide",
            "id": accession,
            "rettype": "fasta",
            "retmode": "text",
        })

        if not response:
            return None

        # Parse FASTA
        lines = response.text.strip().split("\n")
        if not lines or not lines[0].startswith(">"):
            return None

        # Join sequence lines (skip header)
        sequence = "".join(lines[1:]).upper()
        return sequence

    def fetch_cds_sequence(
        self,
        accession: str,
    ) -> Optional[str]:
        """Fetch CDS (coding sequence) only.

        Args:
            accession: RefSeq accession

        Returns:
            CDS sequence string or None
        """
        response = self._make_request("efetch.fcgi", {
            "db": "nucleotide",
            "id": accession,
            "rettype": "fasta_cds_na",
            "retmode": "text",
        })

        if not response:
            return None

        # Parse FASTA
        lines = response.text.strip().split("\n")
        if not lines or not lines[0].startswith(">"):
            return None

        sequence = "".join(lines[1:]).upper()
        return sequence

    def fetch_sequence_for_probe_design(
        self,
        gene_identifier: str,
        species: str = "human",
        sequence_type: str = "mRNA",
    ) -> Optional[Dict]:
        """Fetch sequence suitable for probe design.

        Args:
            gene_identifier: Gene name or RefSeq accession
            species: 'human' or 'mouse'
            sequence_type: 'mRNA' or 'CDS'

        Returns:
            Dict with gene info and sequence, or None
        """
        # Check if it's already an accession
        if gene_identifier.startswith(("NM_", "XM_", "NR_")):
            accession = gene_identifier
            gene_name = gene_identifier
        else:
            # Search for the gene and get RefSeq accession
            accession = self.get_refseq_mrna(gene_identifier, species)
            gene_name = gene_identifier

            if not accession:
                print(f"Could not find RefSeq mRNA for {gene_identifier}")
                return None

        # Fetch sequence based on type
        if sequence_type == "CDS":
            sequence = self.fetch_cds_sequence(accession)
        else:
            sequence = self.fetch_sequence(accession)

        if not sequence:
            print(f"Could not fetch sequence for {accession}")
            return None

        return {
            "gene_name": gene_name,
            "transcript_id": accession,
            "sequence": sequence,
            "length": len(sequence),
            "species": species,
            "sequence_type": sequence_type,
            "source": "NCBI",
        }

    def batch_fetch_sequences(
        self,
        gene_list: List[str],
        species: str = "human",
        sequence_type: str = "mRNA",
    ) -> Dict[str, Optional[Dict]]:
        """Fetch sequences for multiple genes.

        Args:
            gene_list: List of gene names
            species: 'human' or 'mouse'
            sequence_type: 'mRNA' or 'CDS'

        Returns:
            Dict mapping gene names to sequence info
        """
        results = {}
        for gene in gene_list:
            results[gene] = self.fetch_sequence_for_probe_design(gene, species, sequence_type)
        return results
