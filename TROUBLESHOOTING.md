# Troubleshooting Guide

## Common Issues and Solutions

### 1. Read Failed Error for Large AOIs (Czechia_overall)

**Error Message:**
```
rasterio._err.CPLE_AppDefinedError: TIFFFillTile:Read error
RasterioIOError: Read failed. See previous exception for details.
```

**Cause:**
This occurs when processing large overall bounding AOIs (e.g., 1822 km²) due to:
- Network timeouts reading from cloud storage
- Memory issues with very large raster data
- Occasionally corrupted tiles in Planetary Computer storage
- Signed URL expiration during long read operations

**Solutions (in order of preference):**

#### Option 1: Reduce Buffer (Recommended)
Edit `config.yaml`:
```yaml
coordinate_aois:
  overall_buffer_meters: 100  # Reduce from 500 to 100 or even 0
```

#### Option 2: Disable Overall AOI Processing
Edit `config.yaml`:
```yaml
coordinate_aois:
  process_overall: false  # Skip overall AOI entirely
```

#### Option 3: Retry Later
Cloud storage issues are sometimes transient. Try running again after a few minutes.

#### Option 4: Process in Smaller Chunks
If you need the overall AOI:
1. Split your coordinates into smaller groups (2-3 locations each)
2. Process each group separately
3. Merge the results manually in GIS software

### 2. Small/Black Images

**Cause:**
Square AOI size is too small (e.g., 50m = 5×5 pixels at 10m resolution)

**Solution:**
Increase `square_size_meters` in config:
```yaml
coordinate_aois:
  square_size_meters: 1000  # Recommended: 500-2000m
```

**Recommended sizes:**
- 500m → 50×50 pixels (minimum)
- 1000m → 100×100 pixels (good balance)
- 2000m → 200×200 pixels (large context)

### 3. Cloud Cover Issues

**Problem:**
All images are too cloudy

**Solution:**
Adjust cloud cover threshold or date range:
```yaml
sentinel2:
  max_cloud_cover: 30  # Reduce from 100 to get clearer images

coordinate_aois:
  date_range:
    start: "2021-06-01"  # Expand date range
    end: "2021-09-30"
```

### 4. No Images Found

**Cause:**
No Sentinel-2 data available for date range and AOI

**Solutions:**
1. Expand date range
2. Increase `max_cloud_cover`
3. Check if coordinates are correct (format: [latitude, longitude])

### 5. Memory Issues

**Error:**
```
MemoryError: Unable to allocate array
```

**Solutions:**
1. Process fewer dates at once
2. Reduce AOI size
3. Increase available system memory
4. Process locations individually instead of overall AOI

## Configuration Tips

### For Small Detailed Areas (e.g., buildings, fields)
```yaml
coordinate_aois:
  square_size_meters: 500
  overall_buffer_meters: 100
  process_overall: true
```

### For Large Regional Analysis
```yaml
coordinate_aois:
  square_size_meters: 2000
  overall_buffer_meters: 500
  process_overall: false  # Process individually, merge in GIS
```

### For Maximum Reliability (Avoid Timeouts)
```yaml
coordinate_aois:
  square_size_meters: 1000
  overall_buffer_meters: 0
  process_overall: true
```

## Retry Logic

The system now includes automatic retry logic:
- **3 retry attempts** for failed reads
- **2-3 second delays** between retries
- **Re-signs URLs** on retry (handles expiration)

If processing still fails after 3 retries, the system will skip that date and continue.

## Getting Help

If issues persist:

1. Check the error message details
2. Try the solutions above
3. Verify coordinates are in correct format: `[latitude, longitude]`
4. Ensure internet connection is stable
5. Check Planetary Computer status: https://planetarycomputer.microsoft.com/

## Performance Notes

**Processing times (approximate):**
- Individual 1km² AOI: 30-60 seconds per date
- Overall AOI (1800 km²): 5-15 minutes per date (may fail)
- Network speed significantly affects processing time

**Success rates:**
- Small AOIs (<10 km²): ~99% success
- Medium AOIs (10-100 km²): ~95% success
- Large AOIs (>1000 km²): ~70% success (cloud storage dependent)

