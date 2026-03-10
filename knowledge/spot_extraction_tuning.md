# Spot Extraction Parameter Tuning Guide

## Choosing Between Airlocalize and RS-FISH

| Feature | Airlocalize (`use_rsfish: false`) | RS-FISH (`use_rsfish: true`) |
|---------|----------------------------------|------------------------------|
| Speed | Slower (runs per-tile sequentially) | Faster (Spark-distributed) |
| Setup | Simple (no Spark needed) | Requires Spark cluster |
| Tuning | Via parameter files | Via command-line params |
| Per-channel | Via `per_channel_air_localize_params` files | Via `per_channel` map in params JSON |
| Best for | Small/medium datasets, simple setup | Large datasets, HPC/cloud |

## RS-FISH Parameter Tuning

### Most Important Parameters (tune these first)

#### `rsfish_threshold` (default: 0.007)
- **What it does**: Minimum significance score for a spot to be called. Lower = more spots.
- **Too low**: Many false positives (noise called as spots)
- **Too high**: Real spots missed (false negatives)
- **How to tune**:
  1. Start with default 0.007
  2. Look at the output spots overlaid on the image in napari/Fiji
  3. If too many false positives → increase (try 0.01, 0.02, 0.05)
  4. If missing real spots → decrease (try 0.005, 0.003, 0.001)

#### `rsfish_sigma` (default: 1.5)
- **What it does**: Expected Gaussian sigma of spots in pixels.
- **How to tune**: Measure the FWHM of a typical spot in your image, then sigma ≈ FWHM / 2.35
- **Typical values**: 1.0–2.0 for diffraction-limited spots

#### `rsfish_anisotropy` (default: 0.7)
- **What it does**: Ratio accounting for different xy vs z resolution.
- **How to calculate**: `anisotropy = sigma_z / sigma_xy` or approximately `resolution_xy / resolution_z`
- **Example**: With resolution 0.23 µm (xy) and 0.42 µm (z): anisotropy ≈ 0.23/0.42 ≈ 0.55
- **Note**: The default 0.7 is empirically tuned and may differ from the calculated ratio.

### Intensity Parameters

#### `rsfish_min` / `rsfish_max` (defaults: 0, 4096)
- **What they do**: Define the intensity range for the image.
- **rsfish_min**: Set to your camera background/offset level
- **rsfish_max**: Set to your camera bit depth (4096 for 12-bit, 65535 for 16-bit)
- **How to find**: Open your image, check the histogram min/max

#### `rsfish_background` (default: 0)
- 0 = no background subtraction
- Useful if your image has uneven illumination

#### `rsfish_intensity` (default: 0)
- 0 = no intensity normalization
- Useful if spot brightness varies significantly across the field of view

### Per-Channel Tuning
Different channels often have different signal levels and spot characteristics. Use `per_channel` to set different parameters per channel:

```json
{
    "use_rsfish": true,
    "channels": "c0,c1,c2",
    "dapi_channel": "c2",
    "per_channel": {
        "rsfish_threshold": "0.005,0.01",
        "rsfish_sigma": "1.5,1.2",
        "rsfish_min": "100,50",
        "rsfish_max": "4096,4096"
    }
}
```
Note: Values are comma-separated matching the **spot channels** (channels minus dapi_channel), not all channels.

## Airlocalize Parameter Tuning

### Tile Size Parameters
- `airlocalize_xy_stride` (default: 1024): XY tile size
- `airlocalize_z_stride` (default: 512): Z tile size
- `airlocalize_xy_overlap` / `airlocalize_z_overlap`: Auto-calculated (5% of stride, min 50)

**When to adjust**:
- Reduce stride if running out of memory per task
- Increase stride if too many small tiles create overhead
- Increase overlap if spots near tile edges are being missed

### Detection Parameters
Airlocalize uses a parameters file (`default_airlocalize_params`) that controls:
- Spot detection sensitivity
- Gaussian fitting parameters
- Background estimation

**Per-channel tuning**: Create separate parameter files for each channel and specify them via `per_channel_air_localize_params`:
```json
{
    "per_channel_air_localize_params": "/path/to/c0_params.txt,/path/to/c1_params.txt"
}
```

## Common Tuning Scenarios

### "I'm getting too many false positive spots"
1. Increase `rsfish_threshold` (try 2x, e.g., 0.007 → 0.014)
2. Increase `rsfish_min` to exclude background
3. Check if `rsfish_max` matches your image bit depth

### "I'm missing dim spots"
1. Decrease `rsfish_threshold` (try 0.5x, e.g., 0.007 → 0.003)
2. Ensure `rsfish_min` isn't set too high
3. Consider using `spot_extraction_scale: s0` (full resolution)

### "Spots are detected but positions look off"
1. Check `rsfish_sigma` — should match actual spot size
2. Check `rsfish_anisotropy` — must match your z vs xy resolution ratio
3. Verify `resolution` parameter matches actual voxel size

### "Different channels need different sensitivity"
Use `per_channel` overrides — this is very common since FISH probes for different genes can have very different brightness levels.

### "I want to re-run spot extraction without re-running everything"
```bash
nextflow run main.nf -params-file params.json -profile <profile> --skip "stitching,segmentation,registration,warp_spots,measure_intensities,assign_spots" -resume
```
Or use `main-spots-extraction.nf` as the entry point.

## Iterative Tuning Workflow

1. Run spot extraction with defaults
2. Open the stitched image and spots in napari:
   ```python
   import napari, zarr, numpy as np
   viewer = napari.Viewer()
   # Load image
   z = zarr.open('export.n5', 'r')
   viewer.add_image(z['c0/s0'][:], name='c0')
   # Load spots
   spots = np.loadtxt('spots_c0.txt')
   viewer.add_points(spots[:, :3], size=3, name='spots')
   ```
3. Visually inspect: Are spots on real signal? Missing any?
4. Adjust parameters and re-run with `--skip` to skip other steps
5. Repeat until satisfied
