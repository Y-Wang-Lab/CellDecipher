# Input File Formats

## Required Inputs

### CZI Files (Zeiss Image Format)
- **Location**: `{data_dir}/{acq_name}.czi` (or with pattern suffix)
- **Format**: Zeiss CZI microscopy format, multi-tile, multi-channel
- **Naming**: If `stitching_czi_pattern` is set (e.g., `_V%02d`), the pipeline appends this pattern to `acq_name` when looking for CZI files
- **Contents**: Raw tiled microscopy images from EASI-FISH acquisition

### MVL Files (Metadata)
- **Location**: `{data_dir}/{acq_name}.mvl`
- **Format**: Zeiss metadata file containing tile positions for stitching
- **Required for**: Stitching step

## Channel Naming Convention
- Channels are named `c0`, `c1`, `c2`, `c3`, etc. (0-indexed)
- Specified via `channels` parameter: `"c0,c1,c2,c3"`
- `dapi_channel` is typically `c2` (nuclear stain, used for registration and segmentation)
- `bleed_channel` is typically `c3` (channel with bleedthrough from DAPI)
- Spot extraction runs on all channels EXCEPT `dapi_channel`

## Scale Levels
- `s0`: Full resolution
- `s1`: 2x downsampled
- `s2`: 4x downsampled (used for segmentation and deformable registration)
- `s3`: 8x downsampled (used for affine registration)

## Optional Inputs

### Segmentation Model
- **Location**: `{segmentation_model_dir}/` (default: `external-modules/segmentation/my_model`)
- **Format**: StarFinity model files
- **Can be downloaded**: Via `data_manifest` parameter

### Airlocalize Parameters File
- **Location**: Inside container at `/app/airlocalize/params/air_localize_default_params.txt`
- **Override**: Via `default_airlocalize_params` or `per_channel_air_localize_params`

### RS-FISH Custom Parameters
- **Optional**: Via `rsfish_params` parameter pointing to a custom params file

## Data Manifests
- **Location**: `{projectDir}/data-sets/{data_manifest}.txt` or absolute path
- **Format**: Text file with download URLs and MD5 checksums
- **Available**: `demo_tiny`, `demo_small`, `demo_medium`, `segmentation`

## Non-CZI Image Formats

The pipeline natively accepts **CZI + MVL** for stitching. If your images are in a different format (TIFF, ND2, LIF, OME-TIFF, etc.), you can still use the pipeline by converting your data to the N5 format it expects, then skipping the stitching step. There are two approaches depending on whether your images need stitching.

### Required N5 Format (for all non-CZI approaches)

The pipeline expects a specific N5 layout at `{output_dir}/{acq_name}/stitching/export.n5/`. All downstream steps (spot extraction, registration, segmentation) read from this path.

#### Directory Structure
```
export.n5/
├── attributes.json           # Root attributes (can be empty: {})
├── c0/                       # Channel 0
│   ├── attributes.json       # Channel-level attributes (can be empty: {})
│   ├── s0/                   # Full resolution
│   │   └── attributes.json   # MUST have pixelResolution, dimensions, blockSize, dataType
│   ├── s1/                   # 2x downsampled
│   │   └── attributes.json   # MUST have pixelResolution, downsamplingFactors, dimensions, blockSize, dataType
│   ├── s2/                   # 4x downsampled
│   │   └── attributes.json
│   └── s3/                   # 8x downsampled
│       └── attributes.json
├── c1/
│   ├── s0/ ...
│   └── ...
└── ...
```

#### Metadata Format (attributes.json)

**For s0 (full resolution)** — the pipeline reads `pixelResolution.dimensions`:
```json
{
    "pixelResolution": {
        "dimensions": [0.23, 0.23, 0.42],
        "unit": "um"
    },
    "dimensions": [2048, 2048, 256],
    "blockSize": [128, 128, 64],
    "dataType": "uint16"
}
```

**For s1, s2, s3 (downsampled)** — the pipeline reads `pixelResolution * downsamplingFactors`:
```json
{
    "pixelResolution": [0.23, 0.23, 0.42],
    "downsamplingFactors": [2, 2, 2],
    "dimensions": [1024, 1024, 128],
    "blockSize": [128, 128, 64],
    "dataType": "uint16"
}
```

**Critical notes**:
- `dimensions` is in **XYZ order** (N5 convention), NOT ZYX (array shape order)
- `blockSize` is also in XYZ order. Default from the pipeline: `[128, 128, 64]`
- At s0, `pixelResolution` is an **object** with `dimensions` array. At s1+, it is a **plain array**
- `downsamplingFactors` at each level: s1=`[2,2,2]`, s2=`[4,4,4]`, s3=`[8,8,8]`
- The `dimensions` field at each level should reflect the downsampled size (original / factor)
- `dataType` must match your image data type (typically `uint16` or `uint8`)

---

### Option 1: Direct Conversion to N5 (for pre-stitched / single-tile images)

Use this when your images are **already a single fused image** (no tile stitching needed) — e.g., a single TIFF stack, a pre-stitched ND2, an OME-TIFF, or a single Imaris IMS file.

#### What this does
Reads your image file (any format), splits by channel, generates multi-scale downsampled versions (s0–s3), writes the N5 with the exact metadata format EASI-FISH expects.

#### Supported input formats
- **TIFF / OME-TIFF** (`.tif`, `.tiff`) — via `tifffile`
- **Nikon ND2** (`.nd2`) — via `nd2` Python package
- **Leica LIF** (`.lif`) — via `readlif`
- **Imaris IMS** (`.ims`) — via `h5py` (IMS is HDF5-based)

#### Prerequisites
```bash
pip install zarr tifffile numpy scikit-image
# Plus format-specific packages as needed:
pip install nd2        # for .nd2 files
pip install readlif    # for .lif files
pip install h5py       # for .ims files
```

#### Script location
`scripts/convert_to_n5.py` in the multifish-mcp repository.

#### Usage
```bash
# Single multi-channel file (e.g., 4-channel ND2)
python scripts/convert_to_n5.py my_image.nd2 export.n5 \
    --channels c0,c1,c2,c3 --resolution 0.23,0.23,0.42

# Separate TIFF per channel
python scripts/convert_to_n5.py c0.tif,c1.tif,c2.tif,c3.tif export.n5 \
    --channels c0,c1,c2,c3 --resolution 0.23,0.23,0.42

# Single-channel TIFF
python scripts/convert_to_n5.py my_dapi.tif export.n5 \
    --channels c0 --resolution 0.23,0.23,0.42
```

Then place it and run:
```bash
# Move or symlink into the expected location
mkdir -p /path/to/output/Round1/stitching/
mv export.n5 /path/to/output/Round1/stitching/
# Or symlink to avoid moving large data:
# ln -s $(pwd)/export.n5 /path/to/output/Round1/stitching/export.n5

# Run pipeline, skipping stitching
nextflow run main.nf -params-file params.json --skip stitching -resume
```

#### How to find your voxel resolution
- **Fiji**: Open your image → Image → Properties → check "Pixel width", "Pixel height", "Voxel depth"
- **ND2**: In NIS-Elements or `nd2.imread(f).metadata.channels[0].volume.axesCalibration`
- **LIF**: In LAS X software or from the LIF XML metadata
- **If unknown**: Typical EASI-FISH values are `0.23, 0.23, 0.42` µm (XY, Z) for a 40x objective

---

### Option 2: Stitch in Fiji BigStitcher, then convert to EASI-FISH N5

Use this when your images are **multi-tile** (need stitching) but are NOT in CZI format — e.g., tiled TIFFs, ND2 with multiple positions, LIF with tile scan, etc.

**The workflow**: BigStitcher stitches your tiles → exports as N5 → a conversion script restructures the N5 from BigStitcher's layout to EASI-FISH's layout.

#### Step 1: Install BigStitcher in Fiji

1. Open Fiji
2. Help → Update → Manage Update Sites
3. Check **"BigStitcher"** → Apply Changes → Restart Fiji

#### Step 2: Import and stitch your data

1. **Open BigStitcher**: Plugins → BigStitcher → BigStitcher
2. **Define dataset**: Select "define new dataset"
   - For TIFF stacks: choose "ImageJ Openers" or "BioFormats"
   - For ND2/LIF: choose "BioFormats (Bioformats based)"
   - The wizard will ask you to identify tiles, channels, and Z-slices
   - **Tip**: If tiles are in separate files, use "Multiple Images" → specify a pattern like `tile_{xxx}.tif`
3. **Align tiles** (the stitching itself):
   - **Easiest method**: Right-click on all views → "Stitching Wizard"
     - This auto-detects pairwise shifts, filters bad links, and runs global optimization
   - **Manual method** (if wizard doesn't work well):
     - Right-click → Calculate Pairwise Shifts → choose method (Phase Correlation for fluorescence)
     - Right-click → Filter Pairwise Shifts → set correlation threshold (e.g., 0.7)
     - Right-click → Optimize → Global Optimization → choose "Simple (translate only)" or "All transforms"
     - Optionally: Right-click → ICP Refinement (for sub-pixel accuracy)
4. **Verify**: Right-click → Displaying → show in BigDataViewer
   - Check that tiles are aligned correctly (no obvious shifts or gaps)

#### Step 3: Export as N5 from BigStitcher

1. Right-click on all views → **Fuse/Export** → **"As N5"**
2. **Important export settings**:
   - **Output path**: Choose a temporary location (e.g., `/tmp/bigstitcher_export.n5`)
   - **Block size**: Set to `128 x 128 x 64` (matches pipeline default)
   - **Downsampling**: Enable and set levels:
     - Level 0: 1x1x1 (full resolution)
     - Level 1: 2x2x2
     - Level 2: 4x4x4
     - Level 3: 8x8x8
   - **Data type**: Keep as original (typically uint16)
   - **Compression**: "raw" (safest for compatibility)
3. Click OK and wait for export to complete

#### Step 4: Convert BigStitcher N5 to EASI-FISH layout (in-place, no data copy)

BigStitcher exports N5 with a different internal structure:
- **BigStitcher**: `setup{N}/timepoint0/s{L}/` (where N=channel, L=scale level)
- **EASI-FISH expects**: `c{N}/s{L}/`

The conversion script **renames directories in-place** — no data is copied. It only:
- Renames `setup0/timepoint0/s0/` → `c0/s0/` (instant filesystem rename)
- Writes small `attributes.json` metadata files (~200 bytes each)
- Generates missing downsampled levels (s1-s3) only if BigStitcher didn't export them

**Script location**: `scripts/bigstitcher_to_easi.py` in the multifish-mcp repository.

```bash
# Preview what will change (no modifications)
python scripts/bigstitcher_to_easi.py /path/to/export.n5 \
    --channels c0,c1,c2,c3 --resolution 0.23,0.23,0.42 --dry-run

# Apply the conversion (in-place)
python scripts/bigstitcher_to_easi.py /path/to/export.n5 \
    --channels c0,c1,c2,c3 --resolution 0.23,0.23,0.42

# If BigStitcher already created s1-s3, you can skip scale generation:
python scripts/bigstitcher_to_easi.py /path/to/export.n5 \
    --channels c0,c1,c2,c3 --resolution 0.23,0.23,0.42 --no-generate-scales
```

Then symlink or move it into the expected location:
```bash
# Symlink (preferred — avoids moving large data)
ln -s /path/to/export.n5 /path/to/output/Round1/stitching/export.n5

# Or move if on the same filesystem (also instant)
mv /path/to/export.n5 /path/to/output/Round1/stitching/export.n5
```

#### Step 5: Verify and run

```bash
# Check structure
ls /path/to/output/Round1/stitching/export.n5/
# Should show: attributes.json  c0/  c1/  c2/  c3/

cat /path/to/output/Round1/stitching/export.n5/c0/s0/attributes.json
# Should show pixelResolution with dimensions

# Run pipeline
nextflow run main.nf -params-file params.json --skip stitching -resume
```

---

### Format Compatibility Quick Reference

| Format | Multi-tile? | Recommended approach |
|--------|-------------|---------------------|
| TIFF (single image) | No | Option 1 — direct convert to N5, skip stitching |
| OME-TIFF | Maybe | Option 1 if pre-stitched; Option 2 (BigStitcher) if tiled |
| ND2 (Nikon) | Often | Option 2 (BigStitcher → N5) |
| LIF (Leica) | Often | Option 2 (BigStitcher → N5) |
| IMS (Imaris) | No | Option 1 — direct convert to N5 |
| ZARR/N5 | No | Restructure to expected layout (see metadata format above) |
| CZI (Zeiss) | Yes | Native support — no conversion needed |

## Spot File Formats

### Airlocalize Output (`spots_c{N}.txt`)
- Tab-separated values
- Columns: x, y, z (voxel coordinates), intensity

### RS-FISH Output (`spots_rsfish_c{N}.csv`)
- Comma-separated values with header row
- Converted to Airlocalize format by `postprocess_spots`

### Converting Between Formats
- RS-FISH CSV → Airlocalize TXT: The pipeline's `postprocess_spots` step handles this automatically
- The post-processing reads pixel resolution from the N5 `pixelResolution.dimensions` attribute and converts coordinates
