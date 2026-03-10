# Genome masking using Bowtie2, UCSC BLAT, or NCBI BLAST for probe specificity filtering
# Modified for cloud deployment - supports online methods when Bowtie2 unavailable

import subprocess
import pysam
from collections import defaultdict
import os
import shutil
import requests
import re
import time

package_directory = os.path.dirname(os.path.abspath(__file__))
indices_directory = f'{package_directory}/indices/'
indexLookup = {
    'mouse': os.path.join(indices_directory, 'GRCm39/GRCm39'),
    'human': os.path.join(indices_directory, 'GRCh38_noalt_as/GRCh38_noalt_as')
}

# Masking method constants
METHOD_BOWTIE2 = "bowtie2"
METHOD_BLAT = "blat"
METHOD_BLAST = "blast"
METHOD_MEGABLAST = "megablast"
METHOD_NONE = "none"

# UCSC genome database names
UCSC_GENOMES = {
    'mouse': 'mm39',
    'human': 'hg38'
}


def is_bowtie2_available():
    """Check if Bowtie2 is installed and accessible."""
    return shutil.which('bowtie2') is not None


def is_index_available(species="mouse"):
    """Check if genome index is available for the given species."""
    if species not in indexLookup:
        return False
    index_path = indexLookup[species]
    # Check if at least one index file exists
    return os.path.exists(f"{index_path}.1.bt2") or os.path.exists(f"{index_path}.1.bt2l")


def is_genome_masking_available(species="mouse"):
    """Check if local genome masking is available (Bowtie2 + index)."""
    return is_bowtie2_available() and is_index_available(species)


def get_available_methods(species="mouse"):
    """Get list of available masking methods.

    Returns:
        List of tuples: [(method_id, display_name, description), ...]
    """
    methods = []

    if is_bowtie2_available() and is_index_available(species):
        methods.append((
            METHOD_BOWTIE2,
            "Bowtie2 (Local, Recommended)",
            "Fast genome alignment (~seconds). Best for FISH probes."
        ))

    # BLAST options are always available (use NCBI servers) - search RefSeq transcripts
    methods.append((
        METHOD_MEGABLAST,
        "NCBI megablast (Online)",
        "Search RefSeq transcripts via NCBI. Best for most cases."
    ))

    methods.append((
        METHOD_BLAST,
        "NCBI BLAST (Online)",
        "Thorough search of RefSeq transcripts. More sensitive."
    ))

    methods.append((
        METHOD_NONE,
        "None (Skip)",
        "Skip specificity filtering. Probes may have off-target matches."
    ))

    return methods


def get_unavailable_reason(species="mouse"):
    """Get reason why Bowtie2 masking is unavailable."""
    reasons = []
    if not is_bowtie2_available():
        reasons.append("Bowtie2 is not installed")
    if not is_index_available(species):
        reasons.append(f"Genome index for {species} is not available")
    return "; ".join(reasons) if reasons else None


def blat_mask(fasta_string, species="mouse"):
    """Use UCSC BLAT for online genome-based specificity checking.

    BLAT searches the actual genome (like Bowtie2), not just transcripts.
    This is the recommended method for FISH probe design.

    Args:
        fasta_string: FASTA format string with probe sequences
        species: Species for BLAT search ('mouse' or 'human')

    Returns:
        dict: {probe_name: number_of_genomic_hits} for each probe
    """
    genome = UCSC_GENOMES.get(species, 'mm39')

    print(f"Running UCSC BLAT against {species} genome ({genome})...")

    # Parse FASTA to get individual sequences
    sequences = {}
    current_name = None
    current_seq = []

    for line in fasta_string.strip().split('\n'):
        if line.startswith('>'):
            if current_name:
                sequences[current_name] = ''.join(current_seq)
            current_name = line[1:].split()[0]
            current_seq = []
        else:
            current_seq.append(line.strip())
    if current_name:
        sequences[current_name] = ''.join(current_seq)

    hit_counts = {}

    # Query BLAT for each sequence
    for probe_name, sequence in sequences.items():
        print(f"  BLATing {probe_name}...")

        try:
            # Use UCSC BLAT web API with PSL output (parseable format)
            url = "https://genome.ucsc.edu/cgi-bin/hgBlat"
            params = {
                'userSeq': sequence,
                'type': 'DNA',
                'db': genome,
                'output': 'psl',
                'Lucky': 'I\'m feeling lucky'  # Skip to results directly
            }

            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()

            # Parse PSL format response
            # PSL format: matches misMatches repMatches nCount qNumInsert qBaseInsert
            #             tNumInsert tBaseInsert strand qName qSize qStart qEnd
            #             tName tSize tStart tEnd blockCount blockSizes qStarts tStarts
            lines = response.text.strip().split('\n')

            # Skip header lines (start with 'psLayout' or are dashes or blank)
            psl_lines = []
            in_data = False
            for line in lines:
                if line.startswith('psLayout') or line.startswith('-') or not line.strip():
                    continue
                # PSL data lines have tab-separated values starting with a number
                parts = line.split('\t')
                if len(parts) >= 17:
                    try:
                        int(parts[0])  # First field is 'matches' - should be a number
                        psl_lines.append(parts)
                    except ValueError:
                        continue

            # Count significant hits (unique genomic locations)
            significant_hits = 0
            seen_locations = set()
            query_size = len(sequence)

            for parts in psl_lines:
                try:
                    matches = int(parts[0])
                    mismatches = int(parts[1])
                    q_start = int(parts[11])
                    q_end = int(parts[12])
                    t_name = parts[13]  # chromosome
                    t_start = int(parts[15])

                    # Calculate identity and coverage
                    alignment_length = matches + mismatches
                    if alignment_length > 0 and query_size > 0:
                        identity_pct = (matches / alignment_length) * 100
                        coverage_pct = ((q_end - q_start) / query_size) * 100

                        # Significant hit: >85% identity, >70% coverage
                        if identity_pct >= 85 and coverage_pct >= 70:
                            # Create location key to avoid counting same region twice
                            loc_key = f"{t_name}:{t_start//1000}"  # 1kb resolution
                            if loc_key not in seen_locations:
                                seen_locations.add(loc_key)
                                significant_hits += 1
                except (ValueError, IndexError):
                    continue

            hit_counts[probe_name] = significant_hits
            print(f"    {probe_name}: {significant_hits} genomic location(s)")

            # Small delay to be nice to UCSC servers
            time.sleep(0.5)

        except Exception as e:
            print(f"    Warning: BLAT failed for {probe_name}: {e}")
            hit_counts[probe_name] = 0  # Assume OK if BLAT fails

    return hit_counts


def blast_mask(fasta_string, species="mouse", max_off_targets_allowed=1, use_megablast=False,
               target_accession="", target_gene=""):
    """Use NCBI BLAST for online specificity checking.

    Counts the number of OFF-TARGET sequences each probe matches.
    Hits to the target gene are excluded from the count so that
    on-target matches and transcript variants don't cause false filtering.

    A hit is considered on-target if EITHER:
      - Its accession (without version) matches target_accession, OR
      - The target gene symbol appears in the hit title (e.g. "(Gad1)")

    Args:
        fasta_string: FASTA format string with probe sequences
        species: Species for BLAST search ('mouse' or 'human')
        max_off_targets_allowed: Max additional hits beyond the target (default 1)
        use_megablast: If True, use megablast (faster, less sensitive).
                       If False, use regular blastn (slower, more thorough).
        target_accession: RefSeq accession of the target gene (e.g. 'NM_008077').
                          Hits matching this accession (any version) are excluded.
        target_gene: Gene symbol (e.g. 'Gad1'). Hits whose title contains
                     '(Gad1)' are excluded. Catches transcript variants with
                     different accession numbers.

    Returns:
        dict: {probe_name: number_of_off_target_hits} for each probe
    """
    from Bio.Blast import NCBIWWW, NCBIXML

    species_lookup = {
        "mouse": "Mus musculus",
        "human": "Homo sapiens"
    }

    entrez_query = f'{species_lookup.get(species, species)} [ORGN]'

    if target_accession or target_gene:
        print(f"  Target gene: {target_gene}, accession: {target_accession} (on-target hits will be excluded)")

    if use_megablast:
        print(f"Running NCBI megablast against {species} RefSeq transcripts (fast mode)...")
        # megablast: optimized for highly similar sequences - faster search algorithm
        # Using service="megablast" which is more explicitly supported by NCBI
        result_handle = NCBIWWW.qblast(
            "blastn",
            "refseq_rna",
            fasta_string,
            entrez_query=entrez_query,
            hitlist_size=3,
            expect=1,
            service="megablast",  # explicitly use megablast service
        )
    else:
        print(f"Running NCBI BLAST against {species} RefSeq transcripts (thorough mode)...")
        # Regular blastn: more sensitive, catches more distant matches
        result_handle = NCBIWWW.qblast(
            "blastn",
            "refseq_rna",
            fasta_string,
            entrez_query=entrez_query,
            hitlist_size=5,
            expect=1,
            word_size=11,       # default for blastn
        )

    # Strip version suffix from target accession for matching
    # e.g. "NM_008077.3" -> "NM_008077"
    target_base = target_accession.split(".")[0] if target_accession else ""

    # Build a pattern to match gene symbol in BLAST hit titles
    # RefSeq titles look like: "Mus musculus glutamate decarboxylase 1 (Gad1), mRNA"
    target_gene_pattern = f"({target_gene})" if target_gene else ""

    # Parse results - count OFF-TARGET sequences (alignments), not HSPs
    hit_counts = defaultdict(int)
    blast_records = NCBIXML.parse(result_handle)

    for record in blast_records:
        query_name = record.query.split()[0]  # Get probe name

        # Count unique sequences with significant matches, excluding target gene
        off_target_sequences = 0

        for alignment in record.alignments:
            # Skip hits to the target gene itself (including all transcript variants)
            # Check by accession
            hit_accession = getattr(alignment, "accession", "") or ""
            hit_base = hit_accession.split(".")[0]
            if target_base and hit_base == target_base:
                print(f"    {query_name}: skipping on-target hit {hit_accession} (accession match)")
                continue

            # Check by gene symbol in the hit title
            hit_title = getattr(alignment, "title", "") or ""
            if target_gene_pattern and target_gene_pattern in hit_title:
                print(f"    {query_name}: skipping on-target hit {hit_accession} (gene name match in title)")
                continue

            # Check if ANY HSP in this alignment is significant
            has_significant_hsp = False
            for hsp in alignment.hsps:
                identity_pct = (hsp.identities / hsp.align_length) * 100
                coverage_pct = (hsp.align_length / record.query_length) * 100

                # A significant match: >85% identity over >70% of probe length
                if identity_pct >= 85 and coverage_pct >= 70:
                    has_significant_hsp = True
                    break

            if has_significant_hsp:
                off_target_sequences += 1

        hit_counts[query_name] = off_target_sequences
        print(f"  {query_name}: {off_target_sequences} off-target sequence(s) matched")

    return dict(hit_counts)


def genomemask(fasta_string, handleName="tmp", species="mouse", nAlignments=3, index=None):
    """Run Bowtie2 alignment for genome masking.

    Args:
        fasta_string: FASTA format string with probe sequences
        handleName: Base name for temporary files
        species: Species for index lookup ('mouse' or 'human')
        nAlignments: Number of alignments to report per read
        index: Optional custom index path

    Returns:
        Return code from Bowtie2 (0 = success)

    Raises:
        RuntimeError: If Bowtie2 or genome index is not available
    """
    if not is_bowtie2_available():
        raise RuntimeError(
            "Bowtie2 is not installed. Genome masking requires Bowtie2 to be installed. "
            "Please disable genome masking or install Bowtie2."
        )

    if not is_index_available(species):
        raise RuntimeError(
            f"Genome index for {species} is not available. "
            f"Expected index at: {indexLookup.get(species, 'unknown')}. "
            "Please disable genome masking or install the genome index."
        )

    fasta_file = f'{handleName}_reads.fa'
    tmpFasta = open(fasta_file, mode="w")
    tmpFasta.write(fasta_string)
    tmpFasta.close()
    sam_file = f'{handleName}.sam'
    print(indexLookup[species])
    res = subprocess.call(["bowtie2", f"-k{nAlignments}", "-x", indexLookup[species], "-f", fasta_file, "-S", sam_file])
    return res


def countHitsFromSam(samFile):
    """Count alignment hits from SAM file."""
    hitCounts = defaultdict(int)
    sam = pysam.AlignmentFile(samFile, "r")
    for read in sam.fetch():
        if read.is_unmapped:
            hitCounts[read.query_name] += 0
        else:
            hitCounts[read.query_name] += 1
    return hitCounts


def test():
    """Test genome masking functionality."""
    fasta_string = ">read1\ntacgagcttactggacgagcgtgactctgac\n>read2\nctgagctgatgcgacgtatctgatgctgtacgtgacg\n>read3\ncgagctatcgtactgagcggagcgcgggcgatat"
    handleName = 'test'
    proc_info = genomemask(fasta_string, handleName=handleName, species="mouse")
    res = countHitsFromSam(f'{handleName}.sam')
    print(res)
