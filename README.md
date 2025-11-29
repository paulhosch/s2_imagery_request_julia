# Sentinel-2 Imagery Request Tool

Interactive Python script to download and visualize Sentinel-2 true color imagery from Microsoft Planetary Computer.

## Installation

### Requirements

- Python 3.8+
- Microsoft Planetary Computer STAC API access

### Setup

1. Clone the repository:

```bash
git clone https://github.com/paulhosch/s2_imagery_request_julia.git
cd s2_imagery_request_julia
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to configure your AOIs and processing settings:

### Shapefile-based AOIs

Process entire shapefile as single AOI:

```yaml
shapefile_aois:
  - location_name: "Valencia"
    aoi_shapefile: "data/Valencia/Valencia_DANA_für_Paul_Hosch.shp"
    process_as_single: true # Process all features as one unified AOI
    date_range:
      start: "2024-10-29"
      end: "2024-11-05"
```

Process each feature individually:

```yaml
- location_name: "Ahrtal"
  aoi_shapefile: "data/Ahrtal/Paul_Rechtecke_Ahrtal_200_200.shp"
  process_as_single: false # Process each feature individually
  id_field: "fid" # Field containing the rectangle number/ID
  date_range:
    start: "2021-07-15"
    end: "2021-07-19"
```

### Coordinate-based AOIs (e.g., Czechia)

```yaml
coordinate_aois:
  location_group_name: "Czechia"
  square_size_meters: 1000 # Creates 1km x 1km squares
  overall_buffer_meters: 500 # Buffer for overall bounding AOI
  process_overall: true # Create overall bounding image
  date_range:
    start: "2021-07-18"
    end: "2021-07-24"
  coordinates:
    # Format: [latitude, longitude]
    - [50.088622980462404, 16.920334603584177]
    - [50.13685897242434, 17.01203807437035]
    - [50.360140, 17.128160]
```

### Processing Settings

```yaml
sentinel2:
  max_cloud_cover: 100 # Maximum cloud cover percentage
  min_aoi_coverage: 100 # Minimum AOI coverage

output:
  base_dir: "output"
  tif_subdir: "tif"
  jpg_subdir: "jpg"
  jpg_quality: 95 # JPEG quality (0-100)
  target_resolution: 10 # meters/pixel
```

## Usage

Run the interactive script:

```bash
python main.py
```

Or use in Jupyter/VSCode with interactive cells (cells marked with `# %%`).

### True Color Normalization

Uses official Sentinel Hub method:

```python
reflectance = pixel_value / 10000.0
output = reflectance * gain  # gain = 2.5 (default)
```

## How It Works

1. **Query**: Searches Microsoft Planetary Computer STAC catalog for Sentinel-2 L2A images
2. **Filter**: Filters by cloud cover, AOI coverage, and date range
3. **Download**: Streams RGB bands (B04, B03, B02) from cloud storage
4. **Mosaic**: Mosaics multiple tiles if needed (with CRS handling)
5. **Crop**: Crops to AOI geometry
6. **Resample**: Resamples to target resolution (if needed)
7. **Normalize**: Applies true color normalization (official Sentinel Hub method)
8. **Export**: Saves GeoTIFF (native projection) and JPEG (visualization)
9. **Document**: Generates comprehensive metadata documentation

## Credits

- **Data Source**: [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/)
- **Imagery**: Copernicus Sentinel-2 data, ESA
- **True Color Method**: [Sentinel Hub](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/true_color/)
