# Multifish Pipeline Parameters

All parameters with defaults from `param_utils.nf`. Override via params JSON file or command line `--param value`.

## Core Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `acq_names` | `''` | Comma-separated acquisition names to process (e.g., "LHA3_R3_tiny,LHA3_R5_tiny") |
| `ref_acq` | `''` | Reference acquisition for registration and segmentation |
| `shared_work_dir` | `''` | Base directory; auto-configures data_dir, output_dir, spark_work_dir, segmentation_model_dir |
| `data_dir` | `''` | Input directory (auto: `{shared_work_dir}/inputs`) |
| `output_dir` | `''` | Output directory (auto: `{shared_work_dir}/outputs`) |
| `publish_dir` | `''` | Optional final publish directory (e.g., S3 bucket) |
| `channels` | `'c0,c1,c2,c3'` | Comma-separated channel list |
| `dapi_channel` | `'c2'` | DAPI channel for segmentation and registration |
| `bleed_channel` | `'c3'` | Channel needing bleedthrough correction |
| `skip` | `''` | Comma-separated steps to skip |
| `profile` | `'slurm'` | Execution profile |

## Stitching Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `stitching_output` | `'stitching'` | Output subdirectory name |
| `stitching_app` | `'/app/app.jar'` | Stitching JAR path inside container |
| `resolution` | `'0.23,0.23,0.42'` | Voxel resolution x,y,z in microns |
| `axis` | `'-x,y,z'` | Axis mapping |
| `stitching_block_size` | `'128,128,64'` | Block size x,y,z |
| `retile_z_size` | `64` | Z block size for retiling |
| `stitching_mode` | `'incremental'` | `'incremental'` or `'full'` |
| `stitching_padding` | `'0,0,0'` | Padding tuple |
| `stitching_blur_sigma` | `'2'` | Gaussian blur sigma |
| `stitching_czi_pattern` | `''` | CZI naming pattern suffix (e.g., `'_V%02d'`) |
| `flatfield_correction` | `true` | Apply flatfield correction |
| `with_fillBackground` | `true` | Fill background during fusion |

## Spark / Compute Parameters (Stitching)

| Parameter | Default | Description | Tuning |
|-----------|---------|-------------|--------|
| `workers` | `6` | Number of Spark workers | Reduce for small machines |
| `worker_cores` | `8` | CPU cores per worker | CRITICAL: must satisfy `1 (master) + worker_cores + 1 (wait) <= total_CPUs` |
| `gb_per_core` | `15` | GB memory per core | Worker memory = worker_cores * gb_per_core |
| `driver_memory` | `'2g'` | Spark driver memory | |
| `wait_for_spark_timeout_seconds` | `7200` | Spark startup timeout | |
| `sleep_between_timeout_checks_seconds` | `10` | Timeout polling interval | |

## RS-FISH Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_rsfish` | `false` | Use RS-FISH instead of Airlocalize |
| `rsfish_workers` | `6` | Spark workers for RS-FISH |
| `rsfish_worker_cores` | `8` | Cores per RS-FISH worker |
| `rsfish_gb_per_core` | `15` | GB per core for RS-FISH |
| `rsfish_driver_cores` | `1` | Driver cores |
| `rsfish_driver_memory` | `'1g'` | Driver memory |
| `rsfish_min` | `0` | Minimum intensity |
| `rsfish_max` | `4096` | Maximum intensity |
| `rsfish_anisotropy` | `0.7` | Anisotropy factor |
| `rsfish_sigma` | `1.5` | Detection sigma |
| `rsfish_threshold` | `0.007` | Detection threshold |
| `rsfish_background` | `0` | Background method (0=none) |
| `rsfish_intensity` | `0` | Intensity method (0=none) |

Per-channel overrides available via `per_channel` map for: `rsfish_min`, `rsfish_max`, `rsfish_anisotropy`, `rsfish_sigma`, `rsfish_threshold`, `rsfish_background`, `rsfish_intensity`.

## Airlocalize Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `airlocalize_xy_stride` | `0` (→1024) | XY tile stride |
| `airlocalize_xy_overlap` | `0` (→5% of stride, min 50) | XY tile overlap |
| `airlocalize_z_stride` | `0` (→512) | Z tile stride |
| `airlocalize_z_overlap` | `0` (→5% of stride, min 50) | Z tile overlap |
| `airlocalize_cpus` | `1` | CPUs per task |
| `airlocalize_memory` | `'2 G'` | Memory per task |
| `default_airlocalize_params` | `/app/airlocalize/params/air_localize_default_params.txt` | Default params file |
| `per_channel_air_localize_params` | `',,,''` | Per-channel param file overrides |

## Segmentation Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `segmentation_output` | `'segmentation'` | Output subdirectory |
| `segmentation_model_dir` | `'${projectDir}/external-modules/segmentation/my_model'` | StarFinity model directory |
| `segmentation_scale` | `'s2'` | Scale level for segmentation |
| `segmentation_cpus` | `128` | CPUs |
| `segmentation_memory` | `'500 G'` | Memory |
| `segmentation_gpu` | `null` | GPU label (null = no GPU) |
| `segmentation_big` | `'false'` | Big model mode |

## Registration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `aff_scale` | `'s3'` | Scale level for affine alignment |
| `def_scale` | `'s2'` | Scale level for deformable alignment |
| `registration_xy_stride` | `0` (→256) | XY tile stride (must be power of 2) |
| `registration_xy_overlap` | `0` (→stride/8) | XY tile overlap |
| `registration_z_stride` | `0` (→256) | Z tile stride (must be power of 2) |
| `registration_z_overlap` | `0` (→stride/8) | Z tile overlap |
| `spots_cc_radius` | `8` | Cross-correlation radius |
| `spots_spot_number` | `2000` | Number of spots for RANSAC |
| `ransac_cc_cutoff` | `0.9` | RANSAC cross-correlation cutoff |
| `ransac_dist_threshold` | `2.5` | RANSAC distance threshold |
| `deform_iterations` | `'500x200x25x1'` | Deformation iterations per level |
| `deform_auto_mask` | `'0'` | Auto-mask deformation |

## Registration Compute Resources

| Parameter | CPUs | Memory |
|-----------|------|--------|
| `ransac_*` | 1 | 1 G |
| `spots_*` | 1 | 2 G |
| `coarse_spots_*` | 1 | 8 G |
| `interpolate_*` | 1 | 1 G |
| `aff_scale_transform_*` | 1 | 15 G |
| `def_scale_transform_*` | 8 | 80 G |
| `deform_*` | 1 | 4 G |
| `registration_stitch_*` | 2 | 20 G |
| `registration_transform_*` | 12 | 120 G |

## Other Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `warp_spots_cpus` | `3` | CPUs for spot warping |
| `warp_spots_memory` | `'60 G'` | Memory for spot warping |
| `measure_intensities_cpus` | `1` | CPUs for intensity measurement |
| `measure_intensities_memory` | `'50 G'` | Memory for intensity measurement |
| `assign_spots_cpus` | `1` | CPUs for spot assignment |
| `assign_spots_memory` | `'15 G'` | Memory for spot assignment |

## Derived Defaults

When `shared_work_dir` is set, these are auto-configured:
- `data_dir` = `{shared_work_dir}/inputs`
- `output_dir` = `{shared_work_dir}/outputs`
- `segmentation_model_dir` = `{shared_work_dir}/inputs/model/starfinity`
- `spark_work_dir` = `{shared_work_dir}/spark`
- `singularity_cache_dir` = `{shared_work_dir}/singularity`
