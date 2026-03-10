# EASI-FISH / Multifish Pipeline Overview

The EASI-FISH (Expansion-Assisted Iterative Fluorescence In Situ Hybridization) analysis pipeline processes multi-round FISH imaging data through a series of steps: stitching, spot extraction, segmentation, registration, spot warping, intensity measurement, and spot-to-cell assignment.

## Pipeline Steps

### 1. Download (optional)
- Downloads data from a manifest file
- Verifies MD5 checksums
- Container: `downloader:1.1.0`

### 2. Stitching
- Converts CZI files to N5 format using a Spark cluster
- Applies flatfield correction
- Stitches tiled images (incremental or full mode)
- Fuses and retiles the output
- **Uses Spark**: Yes (spark_master, spark_worker, spark_start_app)
- Container: `stitching:1.2.0` (or `1.1.0` in param defaults)
- Output: `{acq_name}/stitching/export.n5`

### 3. Spot Extraction
Two algorithms available, controlled by `use_rsfish` parameter:

#### Airlocalize (default, `use_rsfish: false`)
- Tile-based spot detection
- Processes: `cut_tiles`, `run_airlocalize`, `merge_points`
- **Does NOT use Spark**
- Container: `spot_extraction:1.2.0`

#### RS-FISH (`use_rsfish: true`)
- Spark-based distributed spot detection
- Processes: `prepare_spots_dirs`, spark cluster, `postprocess_spots`
- **Uses Spark**: Yes
- Container for Spark processes: `rs_fish:1.0.2`
- Container for pre/post-processing: `spot_extraction:1.2.0` (airlocalize_container)
- Output: `{acq_name}/spots/spots_rsfish_c{N}.csv` (intermediate), `{acq_name}/spots/spots_c{N}.txt` (final)

### 4. Segmentation
- Cell/nucleus segmentation using StarFinity deep learning model (StarDist3D variant)
- Runs on **reference acquisition only** (`ref_acq` or `segmentation_acq_name`)
- Operates on the **DAPI channel** at the **segmentation scale** (default: `c2/s2`)
- Container: `segmentation:1.0.0`
- Output: `{acq_name}/segmentation/{acq_name}-{dapi_channel}.tif`

#### Segmentation Output Format
The output is a **3D label TIFF** with these properties:
- **Dtype**: uint16 (16-bit unsigned integer)
- **Shape**: (Z, Y, X) matching the N5 image at `segmentation_scale` (default s2 = 4x downsampled)
- **Values**: 0 = background, 1, 2, 3, ... = unique cell/nucleus IDs
- **Compression**: zlib
- Written with: `tifffile.imwrite(path, labels.astype(np.uint16), imagej=True, compression='zlib')`

#### How Downstream Steps Use the Mask
- **assign_spots** (`assign_spots.py`): Loads mask with `tifffile.imread()`, reads voxel spacing from N5 metadata at `segmentation_scale`, converts each spot's micrometer coordinates to voxel indices, looks up the cell label at that voxel. If label > 0, the spot is assigned to that cell. Output: `count.csv` (rows = cell IDs, columns = channels, values = spot counts).
- **measure_intensities** (`intensity_measurements.py`): Loads mask, uses `skimage.measure.regionprops` to compute mean intensity per labeled region. Output: `{channel}_intensity.csv`.

#### Using a Custom Segmentation Model (StarDist-compatible)
If the student has a **StarDist/StarFinity** model, it's a drop-in replacement:
1. Set `segmentation_model_dir` to the model directory path
2. The model directory should contain: `config.json`, `thresholds.json`, `weights_best.h5`
3. If using Singularity, bind-mount the path: `--runtime_opts "-B /path/to/model"`
4. Run normally — no need to skip segmentation

#### Using Pre-Computed Segmentation Masks (CellPose, ilastik, custom, etc.)
If the student already has segmentation results from **any** tool (CellPose, ilastik, Watershed, manual annotation, etc.):

**Questions to ask the student**:
1. What format is your mask in? (TIFF, NumPy .npy, NIfTI, HDF5, etc.)
2. What are the dimensions? (must be 3D: Z, Y, X)
3. What resolution/scale is it at? (full resolution s0, or downsampled?)
4. Is it a label map (0=background, 1,2,3...=cells) or a binary mask?

**Steps to use it**:
1. Convert to uint16 TIFF if not already:
   ```python
   import tifffile, numpy as np
   # If from CellPose:
   tifffile.imwrite('mask.tif', masks.astype(np.uint16), imagej=True, compression='zlib')
   # If from .npy:
   data = np.load('mask.npy')
   tifffile.imwrite('mask.tif', data.astype(np.uint16), imagej=True, compression='zlib')
   ```
2. Place at the expected path:
   ```
   {output_dir}/{acq_name}/segmentation/{acq_name}-{dapi_channel}.tif
   ```
   Use a symlink to avoid copying large data: `ln -s /path/to/mask.tif {output_dir}/{acq_name}/segmentation/{acq_name}-{dapi_channel}.tif`
3. **Dimension matching is critical**: The mask dimensions (Z, Y, X) must match the N5 image at `segmentation_scale`.
   - Default `segmentation_scale` is `s2` (4x downsampled). Check N5 dimensions: `cat export.n5/c2/s2/attributes.json`
   - If the mask is at full resolution (s0), set `segmentation_scale: 's0'` in params JSON
   - If the mask is at a different downsampling, either resample the mask or adjust `segmentation_scale`
4. Run with `--skip segmentation`:
   ```
   nextflow run main.nf -params-file params.json --skip segmentation -resume
   ```

#### Reading the DAPI Image for External Segmentation
If the student wants to run their own segmentation tool, they need to load the DAPI image from the N5:
```python
import zarr
store = zarr.N5Store('/path/to/output/{acq_name}/stitching/export.n5')
root = zarr.open(store, 'r')
dapi = root['c2/s2'][:]  # shape: (Z, Y, X), dtype: uint16
# Run your segmentation on `dapi`, then save the label mask as TIFF
```

### 5. Registration (Bigstream)
- Registers moving acquisitions to fixed reference
- Multi-scale: coarse affine alignment, then per-tile deformable registration
- Steps: tile cutting, coarse spot detection, RANSAC matching, affine transform, fine spot detection, deformable registration, transform stitching, final transform
- Container: `registration:1.2.3`
- Output: `{moving_acq}/registration/{moving_acq}-to-{fixed_acq}/`

### 6. Warp Spots
- Applies registration transforms to detected spots
- Merges warped point files
- Output: `{acq_name}/spots/{moving_acq}-to-{fixed_acq}/spots_c{N}_warped.txt`

### 7. Measure Intensities
- Measures spot intensities on registered images
- Container: `spot_assignment:1.3.0`
- Output: `{acq_name}/intensities/`

### 8. Assign Spots
- Assigns detected spots to segmented cells
- Container: `spot_assignment:1.3.0`
- Output: `{acq_name}/assignments/`

## Entry Points

| File | Purpose |
|------|---------|
| `main.nf` | Full pipeline (all steps) |
| `main-registration.nf` | Registration only |
| `main-assign-spots.nf` | Spot assignment only |
| `main-spots-extraction.nf` | Spot extraction only |
| `main-spots-intensities.nf` | Intensity measurement only |
| `main-warp-spots.nf` | Spot warping only |

## Skipping Steps

Use the `skip` parameter with comma-separated step names:
```
--skip "stitching,segmentation"
```
Valid skip values: `stitching`, `spot_extraction`, `segmentation`, `registration`, `warp_spots`, `measure_intensities`, `assign_spots`

## Key Workflow Logic

- Spot channels = `channels` minus `dapi_channel`
- Registration fixed image defaults to `ref_acq`
- Registration moving images = `acq_names` minus fixed acquisition
- Segmentation runs only on `ref_acq` (or `segmentation_acq_name`)
- Steps can consume pre-existing outputs if run with `-resume` or if outputs already exist
