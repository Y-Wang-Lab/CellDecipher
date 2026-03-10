# Container Images

Default registry: `public.ecr.aws/janeliascicomp/multifish`

## Container Catalog

| Step | Container Name | Default Version | Full Image URI |
|------|---------------|-----------------|----------------|
| Stitching (Spark) | `stitching` | `1.1.0` (param) / `1.2.0` (config override) | `public.ecr.aws/janeliascicomp/multifish/stitching:1.2.0` |
| Spot Extraction (Airlocalize) | `spot_extraction` | `1.2.0` | `public.ecr.aws/janeliascicomp/multifish/spot_extraction:1.2.0` |
| Spot Extraction (RS-FISH) | `rs_fish` | `1.0.2` | `public.ecr.aws/janeliascicomp/multifish/rs_fish:1.0.2` |
| Segmentation | `segmentation` | `1.0.0` | `public.ecr.aws/janeliascicomp/multifish/segmentation:1.0.0` |
| Registration | `registration` | `1.2.3` | `public.ecr.aws/janeliascicomp/multifish/registration:1.2.3` |
| Spot Assignment / Intensities | `spot_assignment` | `1.3.0` | `public.ecr.aws/janeliascicomp/multifish/spot_assignment:1.3.0` |
| Downloader | `downloader` | `1.1.0` | `public.ecr.aws/janeliascicomp/multifish/downloader:1.1.0` |

## Container Contents

### stitching
- Spark 3.x runtime
- Stitching Java application at `/app/app.jar`
- Used by: `spark_master`, `spark_worker`, `spark_start_app` (stitching workflow)

### rs_fish
- Spark 3.x runtime
- RS-FISH Java application at `/app/app.jar` (class: `net.preibisch.rsfish.spark.SparkRSFISH`)
- Built from: `https://github.com/PreibischLab/RS-FISH-Spark.git`
- Used by: `spark_master`, `spark_worker`, `spark_start_app` (rsfish workflow)

### spot_extraction
- Python environment with Airlocalize
- Scripts at `/app/airlocalize/scripts/`
- Default params at `/app/airlocalize/params/air_localize_default_params.txt`
- Also used for RS-FISH pre/post-processing (`prepare_spots_dirs`, `postprocess_spots`)

### segmentation
- StarFinity deep learning model runtime
- GPU support available

### registration
- Bigstream registration toolkit
- Python environment for multi-scale registration

### spot_assignment
- Python tools for intensity measurement and spot-to-cell assignment

## Container Technology

| Profile | Technology | Notes |
|---------|-----------|-------|
| `standard` | Singularity | Default for HPC |
| `localsingularity` | Singularity | Single machine |
| `localdocker` | Docker | Single machine |
| `lsf` | Singularity | IBM LSF scheduler |
| `slurm` | Singularity | SLURM scheduler |
| `tower` / `tower_gpu` | Docker | Seqera Platform |
| `awsbatch` | Docker | AWS Batch |

## Singularity Cache

Singularity images are cached at `{singularity_cache_dir}` (default: `$HOME/.singularity_cache/`).
Image filenames follow the pattern: `public.ecr.aws-janeliascicomp-multifish-{name}-{version}.img`

## Version Note

The `param_utils.nf` defaults `spark_container_version` to `1.1.0`, but the `nextflow.config` `withName` override uses `1.2.0`. The config override takes precedence. This discrepancy exists because the container null fix requires hardcoding the version in config.
