"""File handling utilities."""

import os
import tempfile
from typing import Optional, Tuple
import streamlit as st
import anndata as ad
import pandas as pd


def save_uploaded_file(uploaded_file, suffix: str = "") -> str:
    """Save uploaded file to temporary location and return path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        return tmp_file.name


def load_h5ad_file(file_path: str) -> Optional[ad.AnnData]:
    """Load H5AD file and return AnnData object."""
    try:
        adata = ad.read_h5ad(file_path)
        return adata
    except Exception as e:
        st.error(f"Error loading H5AD file: {str(e)}")
        return None


def save_fasta(sequence: str, name: str, output_dir: str = None) -> str:
    """Save sequence as FASTA file."""
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    file_path = os.path.join(output_dir, f"{name}.fa")
    with open(file_path, "w") as f:
        f.write(f">{name}\n{sequence}\n")
    return file_path


def parse_fasta(file_path: str) -> Tuple[str, str]:
    """Parse FASTA file and return (name, sequence)."""
    name = ""
    sequence = ""
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                name = line[1:].split()[0]
            else:
                sequence += line
    return name, sequence


def export_to_csv(df: pd.DataFrame, filename: str) -> bytes:
    """Convert DataFrame to CSV bytes for download."""
    return df.to_csv(index=False).encode("utf-8")


def export_to_tsv(df: pd.DataFrame, filename: str) -> bytes:
    """Convert DataFrame to TSV bytes for download."""
    return df.to_csv(index=False, sep="\t").encode("utf-8")
