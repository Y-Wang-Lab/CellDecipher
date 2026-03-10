# CellDecipher

An all-in-one tool for EASI-FISH based spatial omics projects.

## Features

- **scRNA-seq Search & Analysis**: Search public databases (CELLxGENE, GEO, HCA) and analyze single-cell data
- **Probe Design**: Design HCR3.0 and BarFISH probes with IDT-compatible output
- **Pipeline Monitor**: Connect to Nextflow Tower to submit and monitor EASI-FISH pipelines
- **Expression Analysis**: QC, clustering, and visualization of gene expression data

## Installation

### Option 1: Clone with Git

```bash
git clone https://github.com/Wang-BrainBody-Lab/CellDecipher.git
cd CellDecipher
```

### Option 2: Download ZIP

1. Go to https://github.com/Wang-BrainBody-Lab/CellDecipher
2. Click the green **"Code"** button
3. Select **"Download ZIP"**
4. Extract the ZIP file
5. Open a terminal and navigate to the extracted folder:
   ```bash
   cd CellDecipher-main
   ```

## Setup

### 1. Create a virtual environment (recommended)

```bash
python -m venv venv
```

Activate the virtual environment:

- **Mac/Linux**:
  ```bash
  source venv/bin/activate
  ```
- **Windows**:
  ```bash
  venv\Scripts\activate
  ```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
streamlit run app.py
```

The app will open in your browser at http://localhost:8501

## Requirements

- Python 3.10 or higher
- For Probe Design with genome masking: [Bowtie2](http://bowtie-bio.sourceforge.net/bowtie2/index.shtml) must be installed

### Installing Bowtie2 (optional, for Probe Design)

- **Mac** (with Homebrew):
  ```bash
  brew install bowtie2
  ```
- **Linux**:
  ```bash
  sudo apt-get install bowtie2
  ```
- **Windows**: Download from [Bowtie2 releases](https://github.com/BenLangmead/bowtie2/releases)

## Troubleshooting

### "Module not found" error
Make sure you activated the virtual environment and installed dependencies:
```bash
source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
```

### Port already in use
Run on a different port:
```bash
streamlit run app.py --server.port 8502
```

### Probe Design not working
Ensure Bowtie2 is installed and the genome index is available.

## License

For internal use only.
