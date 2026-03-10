# Multifish Pipeline Output Structure

## Directory Layout

```
{output_dir}/
├── {acq_name}/                          # One directory per acquisition
│   ├── stitching/
│   │   └── export.n5/                   # Stitched N5 image (multi-channel, multi-scale)
│   │       ├── c0/s0/                   # Channel 0, full resolution
│   │       ├── c0/s1/                   # Channel 0, downsampled 2x
│   │       ├── c0/s2/                   # Channel 0, downsampled 4x
│   │       ├── c0/s3/                   # Channel 0, downsampled 8x
│   │       ├── c1/s0/
│   │       └── ...
│   │
│   ├── spots/                           # Spot extraction results
│   │   ├── spots_c0.txt                 # Final spots (tab-separated: x, y, z, intensity)
│   │   ├── spots_c1.txt
│   │   ├── spots_rsfish_c0.csv          # RS-FISH raw output (if use_rsfish=true)
│   │   ├── spots_rsfish_c1.csv
│   │   └── {moving_acq}-to-{fixed_acq}/ # Warped spots subdirectory
│   │       ├── spots_c0_warped.txt
│   │       └── spots_c1_warped.txt
│   │
│   ├── segmentation/                    # Cell segmentation (ref_acq only)
│   │   └── {acq_name}-{dapi_channel}.tif  # Cell label image (16/32-bit integer)
│   │
│   ├── registration/                    # Registration results
│   │   └── {moving_acq}-to-{fixed_acq}/
│   │       ├── aff/                     # Affine alignment results
│   │       │   ├── fixed_spots.pkl
│   │       │   ├── moving_spots.pkl
│   │       │   └── ransac.mat
│   │       ├── tiles/                   # Per-tile deformable registration
│   │       │   └── tile_{NNNNN}/
│   │       │       ├── coords.txt
│   │       │       ├── fixed_spots.pkl
│   │       │       ├── moving_spots.pkl
│   │       │       ├── ransac.mat
│   │       │       └── deform.mat
│   │       ├── transform/               # Forward transforms per channel
│   │       ├── invtransform/            # Inverse transforms per channel
│   │       └── warped/                  # Warped moving image
│   │           └── export.n5/
│   │
│   ├── intensities/                     # Intensity measurements
│   │   └── {round_name}_intensities_{channel}.csv
│   │
│   └── assignments/                     # Spot-to-cell assignments
│       └── {moving_acq}-to-{fixed_acq}/
│           └── assigned_spots/
```

## Key Output Files

### Stitched Image (`export.n5`)
- Hierarchical N5 format with multi-scale pyramids
- Scale levels: s0 (full), s1 (2x down), s2 (4x), s3 (8x)
- Each channel stored separately: `c0/s0/`, `c1/s0/`, etc.
- Contains `attributes.json` with pixel resolution metadata

### Spots Files
- **`spots_c{N}.txt`**: Final spot coordinates, tab-separated
  - Columns: x, y, z (in voxels), intensity
- **`spots_rsfish_c{N}.csv`**: RS-FISH raw output, comma-separated with header
- **`spots_c{N}_warped.txt`**: Spots transformed to reference coordinate space

### Segmentation Labels
- **`{acq_name}-{dapi_channel}.tif`**: TIFF with integer cell labels
- 0 = background, each positive integer = unique cell ID

### Registration Transforms
- **`transform/`**: Forward transforms (moving → fixed space)
- **`invtransform/`**: Inverse transforms (fixed → moving space)
- **`warped/export.n5/`**: Moving image warped to fixed space

## How to Open / View Output Files

### N5 Images (stitched, warped, registered)
N5 is a chunked array format similar to Zarr, commonly used for large microscopy data.

| Viewer | How to open | Notes |
|--------|-------------|-------|
| **Fiji/ImageJ + N5 Viewer plugin** | Plugins → BigDataViewer → N5 Viewer → select `export.n5` folder | Best for interactive exploration. Install via Fiji update site "N5-Viewer". |
| **Fiji/ImageJ + BigDataViewer** | Plugins → BigDataViewer → Open N5 | Supports multi-scale rendering for large images. |
| **napari + napari-n5** | `napari` then drag-and-drop the `.n5` folder, or `import zarr; data = zarr.open('export.n5')` | Python-based viewer. Install: `pip install napari napari-n5`. |
| **Python (zarr/n5)** | `import zarr; z = zarr.open('export.n5', mode='r'); data = z['c0/s0'][:]` | Direct programmatic access. N5 is compatible with zarr. |
| **BigStitcher (Fiji)** | File → Open with BigStitcher | If you need to re-examine stitching quality. |

### TIFF Images (segmentation labels)
| Viewer | How to open |
|--------|-------------|
| **Fiji/ImageJ** | File → Open → select `.tif` file |
| **napari** | `napari` then drag-and-drop, or `viewer.add_labels(data)` |
| **Python (tifffile)** | `import tifffile; labels = tifffile.imread('file.tif')` |
| **Python (scikit-image)** | `from skimage import io; labels = io.imread('file.tif')` |

### Spots Files (.txt, .csv)
| Tool | How to open |
|------|-------------|
| **Any text editor** | Tab-separated (`.txt`) or comma-separated (`.csv`) |
| **Python (pandas)** | `pd.read_csv('spots_c0.txt', sep='\t', header=None, names=['x','y','z','intensity'])` |
| **Python (numpy)** | `np.loadtxt('spots_c0.txt')` |
| **R** | `read.table('spots_c0.txt')` |
| **Excel** | Open as delimited text file |

### Transform Files (.mat, .pkl)
| File | How to open |
|------|-------------|
| **`.mat` (MATLAB format)** | Python: `scipy.io.loadmat('ransac.mat')`. MATLAB: `load('ransac.mat')` |
| **`.pkl` (Python pickle)** | Python: `import pickle; data = pickle.load(open('file.pkl', 'rb'))` |

### Intensity / Assignment CSVs
| Tool | How to open |
|------|-------------|
| **Python (pandas)** | `pd.read_csv('intensities.csv')` |
| **R** | `read.csv('intensities.csv')` |
| **Excel** | Direct open |

### Tips
- For very large N5 images, always use **BigDataViewer** or **napari** — they stream data on-the-fly instead of loading everything into memory.
- Scale levels (s0, s1, s2, s3) let you view at lower resolution first for fast navigation, then zoom into full resolution (s0).
- Segmentation labels are integer-valued — use `add_labels()` in napari (not `add_image()`) to get color-coded cell IDs.
- Spots files can be overlaid on images in napari using `viewer.add_points(spots[:, :3])`.

## Spark Working Directory
```
{spark_work_dir}/
└── {session_uuid}/
    ├── .sessionId                       # Session identifier file
    ├── spark-defaults.conf              # Spark configuration
    ├── stitching_{acq_name}.log         # Stitching Spark logs
    └── rsFISH_{acq_name}_c{N}.log       # RS-FISH Spark logs
```
These logs are crucial for debugging Spark-related failures.
