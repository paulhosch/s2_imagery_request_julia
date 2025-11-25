# Sentinel-2 Imagery Request Tool

Interactive Python script to download and visualize Sentinel-2 true color imagery from Microsoft Planetary Computer.

## Features

✨ **Dual AOI Support**
- Shapefile-based AOIs (e.g., large regions like Valencia)
- Coordinate-based square AOIs (e.g., specific point locations)
- Automatic overall bounding AOI for coordinate sets

🎨 **True Color Processing**
- Official Sentinel Hub normalization method (linear gain 2.5)
- Consistent, comparable colors across all images
- Bright, natural-looking visualization

📊 **Comprehensive Metadata**
- Automatic `doc.txt` generation for each image
- Includes: projection, resolution, orbit info, cloud cover, processing details
- Full STAC metadata from Sentinel-2 tiles

🗺️ **Smart Projection Handling**
- Native UTM projection (preserves data quality)
- Accurate metric measurements for coordinate squares
- Automatic UTM zone detection

🔄 **Robust Processing**
- Automatic retry logic for cloud storage issues
- Handles multi-tile mosaicking
- Configurable date ranges per AOI type
- Graceful error handling

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

### Shapefile-based AOIs (e.g., Valencia)
```yaml
shapefile_aois:
  - location_name: "Valencia"
    aoi_shapefile: "data/Valencia/Valencia_DANA_für_Paul_Hosch.shp"
    date_range:
      start: "2024-10-29"
      end: "2024-11-05"
```

### Coordinate-based AOIs (e.g., Czechia)
```yaml
coordinate_aois:
  location_group_name: "Czechia"
  square_size_meters: 1000  # Creates 1km x 1km squares
  overall_buffer_meters: 500  # Buffer for overall bounding AOI
  process_overall: true  # Create overall bounding image
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
  max_cloud_cover: 100  # Maximum cloud cover percentage
  min_aoi_coverage: 100  # Minimum AOI coverage

output:
  base_dir: "output"
  tif_subdir: "tif"
  jpg_subdir: "jpg"
  jpg_quality: 95  # JPEG quality (0-100)
  target_resolution: 10  # meters/pixel
```

## Usage

Run the interactive script:

```bash
python main.py
```

Or use in Jupyter/VSCode with interactive cells (cells marked with `# %%`).

### Output Structure

```
output/
├── tif/
│   ├── Valencia/
│   │   ├── Valencia_20241031.tif
│   │   ├── Valencia_20241105.tif
│   │   └── doc.txt
│   ├── Czechia_50_0887N_16_9203E/
│   │   ├── Czechia_50_0887N_16_9203E_20210719.tif
│   │   └── doc.txt
│   └── Czechia_overall/
│       ├── Czechia_overall_20210719.tif
│       └── doc.txt
└── jpg/
    ├── Valencia/
    ├── Czechia_50_0887N_16_9203E/
    └── Czechia_overall/
```

## Key Parameters

### Square AOI Size
- **500m**: Minimum recommended (50×50 pixels at 10m resolution)
- **1000m**: Good balance (100×100 pixels) - **default**
- **2000m**: Large context (200×200 pixels)

### JPEG Quality
- **95**: Excellent quality, minimal artifacts - **default**
- **85-90**: Good quality, smaller files
- **70-85**: Web display

### True Color Normalization
Uses official Sentinel Hub method:
```python
reflectance = pixel_value / 10000.0
output = reflectance * gain  # gain = 2.5 (default)
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions, including:
- Large AOI read failures
- Small/black images
- Cloud cover issues
- Memory problems

### Quick Fixes

**Large AOI failures:**
```yaml
coordinate_aois:
  overall_buffer_meters: 100  # Reduce from 500
  # or
  process_overall: false  # Skip overall AOI
```

**Small images:**
```yaml
coordinate_aois:
  square_size_meters: 1000  # Increase from 50/200
```

## Project Structure

```
.
├── main.py                 # Main processing script
├── config.yaml            # Configuration file
├── requirements.txt       # Python dependencies
├── TROUBLESHOOTING.md    # Troubleshooting guide
├── src/
│   ├── aoi_handler.py    # AOI creation and management
│   ├── image_processor.py # Image processing and normalization
│   └── sentinel2_query.py # STAC API queries
├── data/                  # Input shapefiles
└── output/               # Generated images and metadata
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
- **Imagery**: Copernicus Sentinel-2 data
- **True Color Method**: [Sentinel Hub](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/true_color/)

## License

MIT License - see LICENSE file for details

## Author

Paul Hosch - [GitHub](https://github.com/paulhosch)

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## Changelog

### v1.0.0 (2024)
- Initial release
- Shapefile and coordinate-based AOI support
- True color normalization (Sentinel Hub method)
- Automatic metadata documentation
- Overall bounding AOI functionality
- Retry logic for large AOIs
- Comprehensive error handling
