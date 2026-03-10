# Known Errors and Solutions

## ERROR: Container resolving to null

### Symptoms
- Error message: `container: 'null'` or process fails to find container image
- Affects all Spark processes: `spark_master`, `spark_worker`, `spark_start_app`, etc.

### Root Cause
`external-modules/spark/lib/processes.nf` uses eager GString evaluation:
```groovy
container = "${params.spark_container_repo}/..."
```
In Nextflow 25.x, this evaluates at parse/include time before params are populated, resulting in `null`.

### Fix
Add `withName` blocks to `nextflow.config` in the `process {}` section:
```groovy
// Spark infrastructure processes
withName: 'prepare_spark_work_dir|spark_master|spark_worker|wait_for_master|wait_for_worker|terminate_spark' {
    container = 'public.ecr.aws/janeliascicomp/multifish/stitching:1.2.0'
}
// Workflow-specific spark_start_app
withName: 'stitching:.*:spark_start_app' {
    container = 'public.ecr.aws/janeliascicomp/multifish/stitching:1.2.0'
}
withName: 'spot_extraction:.*:spark_start_app' {
    container = 'public.ecr.aws/janeliascicomp/multifish/rs_fish:1.0.2'
}
```

### Important Note
Do NOT use a single blanket `withName` for all Spark processes including `spark_start_app`. The `spark_start_app` process is reused by multiple workflows (stitching and rsfish), and each needs its own container. Using a blanket stitching container for rsfish's `spark_start_app` causes exit code 101 because the stitching container doesn't have the RS-FISH JAR.

### Affected Versions
Nextflow 25.x and later. Older versions evaluated GString container directives lazily.

---

## ERROR: spark_worker stuck at NEW (CPU resource deadlock)

### Symptoms
- `spark_worker` process stays in NEW/SUBMITTED state indefinitely
- `wait_for_worker` runs but never completes
- Pipeline appears hung

### Root Cause
Local executor enforces CPU constraints. With N total CPUs:
- `spark_master` reserves 1 CPU
- `wait_for_worker` reserves 1 CPU
- `spark_worker` requests `worker_cores` CPUs

If `1 + 1 + worker_cores > total_CPUs`, the worker can never be scheduled.

### Fix
Reduce `worker_cores` in params JSON:
```
worker_cores <= total_CPUs - 2
```
For a 4-CPU machine, `worker_cores` must be <= 2.

Same applies to `rsfish_worker_cores` for the RS-FISH step.

---

## ERROR: spark_start_app exit code 101 (wrong container)

### Symptoms
- `spark_start_app` exits with code 101
- Error occurs during `spot_extraction:rsfish:run_rsfish:spark_start_app`
- The command tries to run `--class net.preibisch.rsfish.spark.SparkRSFISH` but fails

### Root Cause
The `spark_start_app` process is using the stitching container instead of the RS-FISH container. The stitching container doesn't have the RS-FISH JAR (`/app/app.jar` with SparkRSFISH class).

### Fix
Use workflow-scoped `withName` selectors instead of a blanket override. See "Container resolving to null" fix above.

---

## ERROR: postprocess_spots FileNotFoundError

### Symptoms
```
FileNotFoundError: /path/to/spots/spots_rsfish_c0.csv not found.
```
- `postprocess_spots` fails because the RS-FISH output CSV doesn't exist

### Root Cause
This is a downstream consequence. The upstream `spark_start_app` (RS-FISH) either:
1. Failed with the wrong container (exit 101)
2. Was interrupted (check for `WARN: Got an interrupted exception`)
3. Ran out of memory or resources

### Fix
Fix the upstream issue first. Check the Spark log at:
```
{spark_work_dir}/{session_uuid}/rsFISH_{acq_name}_c{N}.log
```

---

## ERROR: Timed out waiting for .sessionId file

### Symptoms
```
ERROR: Timed out after N seconds while waiting for /path/.sessionId
```

### Root Cause
- Spark master failed to start and write the session file
- `spark_work_dir` is not accessible to all nodes
- Network/filesystem issues between nodes

### Fix
1. Check that `spark_work_dir` is on a shared filesystem accessible to all nodes
2. Check Spark master logs in the work directory
3. Increase `wait_for_spark_timeout_seconds` if startup is slow

---

## ERROR: Session ID mismatch

### Symptoms
```
ERROR: session id in .sessionId does not match current session
```

### Root Cause
A stale `.sessionId` file from a previous run exists in `spark_work_dir`. Multiple pipelines may be sharing the same `spark_work_dir`.

### Fix
1. Clean the `spark_work_dir` directory
2. Use a unique `spark_work_dir` for each pipeline run
3. Or delete the specific session UUID directory

---

## WARNING: SINGULARITYENV vs APPTAINERENV

### Symptoms
```
INFO: Environment variable SINGULARITYENV_NXF_TASK_WORKDIR is set, but APPTAINERENV_NXF_TASK_WORKDIR is preferred
```

### Root Cause
Newer versions of Singularity have been renamed to Apptainer. The environment variable prefix changed from `SINGULARITYENV_` to `APPTAINERENV_`.

### Fix
This is just a warning and doesn't affect execution. Can be ignored safely. To suppress, update Nextflow or set `APPTAINERENV_` variables instead.

---

## ERROR: addParams not reaching sub-workflows

### Symptoms
- Parameters set in the JSON file are not being picked up by nested workflows
- Container or other settings resolve to defaults instead of user values

### Root Cause
Nextflow DSL2 `addParams` is deprecated and doesn't reliably pass parameters to transitive sub-includes (workflows that include other workflows).

### Fix
Use `withName` blocks in `nextflow.config` for container overrides rather than relying on `addParams` chains.
