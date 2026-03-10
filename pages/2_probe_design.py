"""Probe Design Page - HCR3.0 and BarFISH probe design."""

import streamlit as st
import pandas as pd
import tempfile
import os
from typing import Dict, List, Optional

# Import services
import sys
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, app_dir)
sys.path.insert(0, os.path.join(app_dir, "probe_design_lib"))

from services.ncbi_service import NCBIService
from services.ucsc_ensembl_service import UCSCEnsemblService
from services.probe_service import ProbeDesignService, ProbeDesignParams
from utils.file_handlers import save_fasta, export_to_csv, export_to_tsv
from components.progress_indicators import StepProgress

# Initialize services
@st.cache_resource
def get_ncbi_service():
    return NCBIService()

@st.cache_resource
def get_ucsc_ensembl_service():
    return UCSCEnsemblService()

@st.cache_resource
def get_probe_service():
    return ProbeDesignService()


# Page header
st.title("🧬 DNA Probe Design")
st.markdown("Design HCR3.0 or BarFISH probes for your target genes")

# Initialize session state
if "gene_sequences" not in st.session_state:
    st.session_state.gene_sequences = {}
if "gene_channel_mapping" not in st.session_state:
    st.session_state.gene_channel_mapping = {}
if "probe_results" not in st.session_state:
    st.session_state.probe_results = {}

# Mode selection
st.subheader("1. Select Probe Type")
probe_mode = st.radio(
    "Choose probe design mode:",
    ["HCR3.0 Probes", "BarFISH Probes"],
    horizontal=True,
    help="HCR3.0: Standard split-initiator probes. BarFISH: Barcoded multiplexed probes."
)

is_hcr = probe_mode == "HCR3.0 Probes"

# Species, sequence source, and sequence type selection
col1, col2, col3 = st.columns(3)
with col1:
    species = st.selectbox(
        "Species",
        ["mouse", "human"],
        help="Select the species for genome masking"
    )

with col2:
    sequence_source = st.selectbox(
        "Sequence Source",
        ["Ensembl", "NCBI"],
        help="Ensembl: ENSMUST/ENST transcripts. NCBI: RefSeq from Entrez."
    )

with col3:
    sequence_type = st.selectbox(
        "Sequence Type",
        ["mRNA", "CDS", "genomic"],
        help="mRNA: spliced transcript (exons only). CDS: coding sequence only. genomic: unspliced with introns."
    )

st.divider()

# Gene input section
st.subheader("2. Input Genes")

input_method = st.radio(
    "How would you like to input genes?",
    ["Enter gene names/IDs", "Upload FASTA file"],
    horizontal=True
)

ncbi_service = get_ncbi_service()
ucsc_ensembl_service = get_ucsc_ensembl_service()
probe_service = get_probe_service()

if input_method == "Enter gene names/IDs":
    # Show appropriate placeholder based on source
    if sequence_source == "Ensembl":
        placeholder = "Gad1\nSnap25\nENSMUST00000028417"
        input_help = "Enter gene names or Ensembl transcript IDs (ENSMUST/ENST)"
    else:  # NCBI
        placeholder = "Gad1\nSnap25\nNM_001412615"
        input_help = "Enter gene names or RefSeq accessions (NM_*)"

    st.markdown(f"Enter gene names or IDs (one per line) - *{input_help}*:")
    gene_input = st.text_area(
        "Genes",
        height=150,
        placeholder=placeholder,
        label_visibility="collapsed"
    )

    if st.button(f"🔍 Fetch Sequences from {sequence_source}", type="primary"):
        if gene_input.strip():
            genes = [g.strip() for g in gene_input.strip().split("\n") if g.strip()]

            progress = StepProgress(
                [f"Fetching {g}" for g in genes],
                st.container()
            )
            progress.start()

            for i, gene in enumerate(genes):
                progress.set_step(i, f"Looking up {gene} in {sequence_source}...")

                if sequence_source == "NCBI":
                    result = ncbi_service.fetch_sequence_for_probe_design(gene, species, sequence_type)
                else:
                    result = ucsc_ensembl_service.fetch_sequence_for_probe_design(
                        gene, species, source=sequence_source, sequence_type=sequence_type
                    )

                if result:
                    st.session_state.gene_sequences[gene] = result
                    transcript_id = result.get('transcript_id', 'N/A')
                    source = result.get('source', sequence_source)
                    st.success(f"✓ {gene}: {result['length']} bp (transcript: {transcript_id}, source: {source})")
                else:
                    st.warning(f"✗ {gene}: Could not fetch sequence from {sequence_source}")

            progress.complete(f"Fetched {len(st.session_state.gene_sequences)} sequences")
        else:
            st.warning("Please enter at least one gene name")

else:  # Upload FASTA
    uploaded_files = st.file_uploader(
        "Upload FASTA file(s)",
        type=["fa", "fasta", "fna"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            content = uploaded_file.read().decode("utf-8")
            # Parse FASTA
            name = ""
            sequence = ""
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith(">"):
                    if name and sequence:
                        st.session_state.gene_sequences[name] = {
                            "gene_name": name,
                            "sequence": sequence,
                            "length": len(sequence),
                            "species": species,
                        }
                    name = line[1:].split()[0]
                    sequence = ""
                else:
                    sequence += line
            # Add last sequence
            if name and sequence:
                st.session_state.gene_sequences[name] = {
                    "gene_name": name,
                    "sequence": sequence,
                    "length": len(sequence),
                    "species": species,
                }
        st.success(f"Loaded {len(st.session_state.gene_sequences)} sequences")

# Display fetched sequences
if st.session_state.gene_sequences:
    st.divider()
    st.subheader("3. Gene-Channel Assignment")

    # Get available channels
    if is_hcr:
        available_channels = probe_service.get_hcr_channels()
    else:
        available_channels = probe_service.get_barcode_list(limit=1000)

    # Assign channels to each gene
    st.markdown("**Assign channel to each gene:**")

    for gene in st.session_state.gene_sequences.keys():
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**{gene}**")
        with col2:
            if is_hcr:
                current_idx = 0
                current_val = st.session_state.gene_channel_mapping.get(gene)
                if current_val in available_channels:
                    current_idx = available_channels.index(current_val)

                selected = st.selectbox(
                    f"Channel for {gene}",
                    available_channels,
                    key=f"channel_{gene}",
                    index=current_idx,
                    label_visibility="collapsed"
                )
            else:
                search_query = st.text_input(
                    f"Search barcode for {gene}",
                    key=f"search_{gene}",
                    label_visibility="collapsed",
                    placeholder="Search barcode..."
                )
                if search_query:
                    filtered = probe_service.search_barcodes(search_query)
                else:
                    filtered = available_channels[:50]

                selected = st.selectbox(
                    f"Barcode for {gene}",
                    filtered,
                    key=f"channel_{gene}",
                    label_visibility="collapsed"
                )

            st.session_state.gene_channel_mapping[gene] = selected

    # Show current assignments
    st.markdown("---")
    st.markdown("**Current Assignments:**")

    assignment_data = []
    for gene, seq_info in st.session_state.gene_sequences.items():
        current_channel = st.session_state.gene_channel_mapping.get(gene, available_channels[0] if available_channels else "")
        # Initialize mapping if not set
        if gene not in st.session_state.gene_channel_mapping:
            st.session_state.gene_channel_mapping[gene] = current_channel
        assignment_data.append({
            "Gene": gene,
            "Length (bp)": seq_info["length"],
            "Channel": st.session_state.gene_channel_mapping.get(gene, current_channel),
        })

    df = pd.DataFrame(assignment_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Show sequence preview
    with st.expander("📄 View Sequences"):
        for gene, seq_info in st.session_state.gene_sequences.items():
            seq_type = seq_info.get('sequence_type', 'mRNA')
            transcript_id = seq_info.get('transcript_id', '')
            source = seq_info.get('source', 'NCBI')
            st.markdown(f"**{gene}** ({seq_info['length']} bp) - {seq_type}, {transcript_id} ({source})")
            seq = seq_info["sequence"]
            # Show first 500 bp
            display_seq = seq[:500] + ("..." if len(seq) > 500 else "")
            st.code(display_seq, language=None)

    st.divider()

    # Design parameters
    st.subheader("4. Design Parameters")

    col1, col2, col3 = st.columns(3)

    with col1:
        max_probes = st.slider("Max probes per gene", 5, 50, 20)
        min_gc = st.slider("Min GC%", 30.0, 50.0, 38.0)

    with col2:
        max_gc = st.slider("Max GC%", 50.0, 70.0, 62.0)
        min_gibbs = st.slider("Min Gibbs (kcal/mol)", -80.0, -60.0, -70.0)

    with col3:
        max_gibbs = st.slider("Max Gibbs (kcal/mol)", -60.0, -40.0, -50.0)
        num_overlap = st.slider("Max overlap (bp)", 0, 20, 10)

    with st.expander("⚙️ Advanced Options"):
        # Get available masking methods
        try:
            from genomeMask import get_available_methods, METHOD_BOWTIE2, METHOD_BLAST, METHOD_MEGABLAST, METHOD_NONE
            available_methods = get_available_methods(species)
        except ImportError:
            available_methods = [("none", "None (Skip)", "Masking module not available")]
            METHOD_BOWTIE2, METHOD_BLAST, METHOD_MEGABLAST, METHOD_NONE = "bowtie2", "blast", "megablast", "none"

        # Create options for selectbox
        method_ids = [m[0] for m in available_methods]
        method_names = [m[1] for m in available_methods]
        method_descriptions = {m[0]: m[2] for m in available_methods}

        # Default to first available method (Bowtie2 if local, BLAST otherwise)
        default_idx = 0

        masking_method = st.selectbox(
            "Specificity filtering method",
            options=method_ids,
            format_func=lambda x: dict(zip(method_ids, method_names))[x],
            index=default_idx,
            help="Filter probes that match multiple genome/transcript locations"
        )

        # Show description of selected method
        st.caption(f"ℹ️ {method_descriptions[masking_method]}")

        # Convert to genomemask boolean for backward compatibility
        # (probeDesign.py expects genomemask=True/False)
        genomemask = masking_method == METHOD_BOWTIE2

        # Store the method for online filtering (BLAST)
        st.session_state.masking_method = masking_method

        # Repeat masking disabled - RepeatMasker API is unreliable
        repeatmask = False

    st.divider()

    # Run probe design
    st.subheader("5. Run Probe Design")

    if st.button("🚀 Design Probes", type="primary", use_container_width=True):
        # Determine which filtering method to use
        current_method = st.session_state.get("masking_method", "none")
        use_blast = current_method in ("blast", "megablast")
        use_megablast = current_method == "megablast"

        params = ProbeDesignParams(
            species=species,
            max_probes=max_probes,
            min_gc=min_gc,
            max_gc=max_gc,
            min_gibbs=min_gibbs,
            max_gibbs=max_gibbs,
            num_overlap=num_overlap,
            genomemask=genomemask,  # Only True for Bowtie2
            repeatmask=repeatmask,
        )

        genes_to_process = list(st.session_state.gene_sequences.keys())

        # Build step list
        steps = [f"Designing probes for {g}" for g in genes_to_process]
        if use_blast:
            blast_type = "megablast" if use_megablast else "BLAST"
            steps.append(f"Running NCBI {blast_type} for specificity filtering...")

        progress = StepProgress(steps, st.container())
        progress.start()

        for i, gene in enumerate(genes_to_process):
            progress.set_step(i, f"Processing {gene}...")

            seq_info = st.session_state.gene_sequences[gene]
            channel = st.session_state.gene_channel_mapping.get(gene, available_channels[0])

            # Save sequence to temp FASTA
            with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False) as f:
                f.write(f">{gene}\n{seq_info['sequence']}\n")
                fasta_path = f.name

            try:
                if is_hcr:
                    result = probe_service.design_hcr_probes(
                        fasta_path=fasta_path,
                        gene_name=gene,
                        channel=channel,
                        params=params,
                    )
                else:
                    result = probe_service.design_barfish_probes(
                        fasta_path=fasta_path,
                        gene_name=gene,
                        barcode_name=channel,
                        params=params,
                    )

                st.session_state.probe_results[gene] = result

                if result.success:
                    st.success(f"✓ {gene}: {result.total_probes} probes designed")
                else:
                    st.error(f"✗ {gene}: {result.error_message}")

            finally:
                if os.path.exists(fasta_path):
                    os.unlink(fasta_path)

        # Run BLAST filtering if selected
        if use_blast and any(r.success for r in st.session_state.probe_results.values()):
            time_estimate = "~20-60 sec" if use_megablast else "~1-3 min"
            progress.set_step(len(genes_to_process), f"Running NCBI {blast_type} ({time_estimate} per gene)...")

            try:
                from genomeMask import blast_mask

                for gene, result in st.session_state.probe_results.items():
                    if not result.success or not result.probes:
                        continue

                    # Build FASTA of probe sequences
                    fasta_lines = []
                    for probe in result.probes:
                        fasta_lines.append(f">{probe['name']}")
                        fasta_lines.append(probe['sequence'])
                    fasta_string = "\n".join(fasta_lines)

                    # Get target accession to exclude on-target hits
                    seq_info = st.session_state.gene_sequences.get(gene, {})
                    target_accession = seq_info.get("transcript_id", "")

                    # Run BLAST filtering
                    st.info(f"Running {blast_type} for {gene} ({len(result.probes)} probes)...")
                    hit_counts = blast_mask(
                        fasta_string, species=species,
                        use_megablast=use_megablast,
                        target_accession=target_accession,
                        target_gene=gene,
                    )

                    # Filter probes with off-target hits (target gene excluded from count)
                    original_count = len(result.probes)
                    filtered_probes = [
                        p for p in result.probes
                        if hit_counts.get(p['name'], 0) == 0
                    ]

                    # Update result
                    result.probes = filtered_probes
                    result.total_probes = len(filtered_probes)

                    removed = original_count - len(filtered_probes)
                    if removed > 0:
                        st.warning(f"{blast_type} filtered {removed} non-specific probes from {gene}")
                    else:
                        st.success(f"All {original_count} probes passed {blast_type} specificity check")

            except Exception as e:
                st.error(f"BLAST filtering failed: {e}")
                import traceback
                st.code(traceback.format_exc())

        progress.complete("Probe design complete!")

    # Display results
    if st.session_state.probe_results:
        st.divider()
        st.subheader("6. Results")

        # Summary metrics
        total_probes = sum(r.total_probes for r in st.session_state.probe_results.values())
        total_cost = sum(r.estimated_cost for r in st.session_state.probe_results.values())
        successful = sum(1 for r in st.session_state.probe_results.values() if r.success)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Genes", len(st.session_state.probe_results))
        col2.metric("Successful", successful)
        col3.metric("Total Probes", total_probes)
        col4.metric("Est. Cost", f"${total_cost:.2f}")

        # Results table
        tabs = st.tabs(["Summary", "IDT Format", "Per Gene"])

        with tabs[0]:
            # Combined summary
            all_probes = []
            for gene, result in st.session_state.probe_results.items():
                if result.success:
                    for p in result.probes:
                        all_probes.append({
                            "Gene": gene,
                            "Channel": p["channel"],
                            "Name": p["name"],
                            "Start": p["start"],
                            "GC%": f"{p['GC']:.1f}",
                            "Gibbs": f"{p['Gibbs']:.1f}",
                        })

            if all_probes:
                summary_df = pd.DataFrame(all_probes)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

        with tabs[1]:
            # IDT format
            all_idt_rows = []
            for gene, result in st.session_state.probe_results.items():
                if result.success:
                    idt_df = probe_service.format_idt_output(result.probes)
                    all_idt_rows.extend(idt_df.to_dict('records'))

            if all_idt_rows:
                idt_df = pd.DataFrame(all_idt_rows)
                st.dataframe(idt_df, use_container_width=True, hide_index=True)

                # Download button
                csv_data = idt_df.to_csv(index=False, sep='\t').encode('utf-8')
                st.download_button(
                    "📥 Download IDT Format (TSV)",
                    csv_data,
                    file_name="probes_idt_format.tsv",
                    mime="text/tab-separated-values",
                    type="primary"
                )

        with tabs[2]:
            # Per gene details
            for gene, result in st.session_state.probe_results.items():
                with st.expander(f"{gene} - {result.total_probes} probes (${result.estimated_cost:.2f})"):
                    if result.success:
                        detail_df = probe_service.format_summary_table(result.probes)
                        st.dataframe(detail_df, use_container_width=True, hide_index=True)
                    else:
                        st.error(result.error_message)

        # Gene-Channel mapping summary
        st.divider()
        st.subheader("Gene-Channel Mapping")
        mapping_df = pd.DataFrame([
            {"Gene": gene, "Channel": st.session_state.gene_channel_mapping.get(gene, "N/A")}
            for gene in st.session_state.gene_sequences.keys()
        ])
        st.dataframe(mapping_df, use_container_width=True, hide_index=True)

        # Download mapping
        mapping_csv = mapping_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download Gene-Channel Mapping",
            mapping_csv,
            file_name="gene_channel_mapping.csv",
            mime="text/csv"
        )

# Clear button
st.divider()
if st.button("🗑️ Clear All Data"):
    st.session_state.gene_sequences = {}
    st.session_state.gene_channel_mapping = {}
    st.session_state.probe_results = {}
    st.rerun()
