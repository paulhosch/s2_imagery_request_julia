"""
Interactive script to download Sentinel-2 True Color images for AOIs.
Supports both shapefile-based AOIs and coordinate-based square AOIs.
Uses # %% cells for interactive execution in IDEs like VSCode or Jupyter.
"""

# %%
import yaml
import os
import numpy as np
from pathlib import Path
from src.aoi_handler import load_aoi, create_square_aoi_from_coordinates, create_overall_bounding_aoi
from src.sentinel2_query import search_sentinel2_images
from src.image_processor import (
    load_and_crop_bands,
    resample_to_resolution,
    normalize_for_display,
    export_geotiff,
    export_jpeg,
    write_metadata_doc
)

# %%
# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

print("=" * 80)
print("SENTINEL-2 TRUE COLOR IMAGE DOWNLOADER")
print("=" * 80)
print("\nConfiguration loaded:")
print(f"  Shapefile AOIs: {len(config.get('shapefile_aois', []))}")
print(f"  Coordinate AOIs: {len(config.get('coordinate_aois', {}).get('coordinates', []))}")
print(f"  Max cloud cover: {config['sentinel2']['max_cloud_cover']}%")


# %%
# Process shapefile-based AOIs
def process_aoi(location_name, aoi_geometry, bounds, start_date, end_date, config, output_folder=None):
    """Process a single AOI (shapefile or coordinate-based).
    
    Args:
        location_name: Name used for filenames
        aoi_geometry: Shapely geometry of the AOI
        bounds: Bounding box of the AOI
        start_date: Start date for imagery search
        end_date: End date for imagery search
        config: Configuration dictionary
        output_folder: Optional folder name (if different from location_name)
    """
    
    print(f"\nSearching for Sentinel-2 images...")
    print(f"  Date range: {start_date} to {end_date}")
    
    dates_dict = search_sentinel2_images(
        bounds=bounds,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=config['sentinel2']['max_cloud_cover'],
        aoi_geometry=aoi_geometry
    )

    if len(dates_dict) == 0:
        print("  ⚠ No suitable images found.")
        return
    
    print(f"\n{'='*60}")
    print(f"Processing {len(dates_dict)} dates for {location_name}...")
    print(f"{'='*60}")
    
    for idx, (date, items) in enumerate(sorted(dates_dict.items()), 1):
        print(f"\n[{idx}/{len(dates_dict)}] Processing {date}...")
        print(f"  Tiles to mosaic: {len(items)}")
        
        # Calculate average cloud cover
        avg_cloud = sum(item.properties.get('eo:cloud_cover', 0) for item in items) / len(items)
        print(f"  Average cloud cover: {avg_cloud:.1f}%")
        
        # Create output filenames with location-specific subdirectories
        location_safe = location_name.replace(' ', '_')
        date_str = date.replace('-', '')
        base_filename = f"{location_safe}_{date_str}"
        
        # Use output_folder if provided, otherwise use location_name
        folder_name = output_folder.replace(' ', '_') if output_folder else location_safe
        
        # Create subdirectories for this location
        tif_location_dir = os.path.join(
            config['output']['base_dir'],
            config['output']['tif_subdir'],
            folder_name
        )
        jpg_location_dir = os.path.join(
            config['output']['base_dir'],
            config['output']['jpg_subdir'],
            folder_name
        )
        
        # Ensure directories exist
        os.makedirs(tif_location_dir, exist_ok=True)
        os.makedirs(jpg_location_dir, exist_ok=True)
        
        tif_path = os.path.join(tif_location_dir, f"{base_filename}.tif")
        jpg_path = os.path.join(jpg_location_dir, f"{base_filename}.jpg")
        
        # Check if files already exist
        files_exist = os.path.exists(tif_path) and os.path.exists(jpg_path)
        
        if files_exist:
            print(f"  ℹ️  Images already exist")
            
            # Always (re)generate doc.txt even if images exist
            print(f"  Regenerating metadata documentation...")
            try:
                # Need to get profile from existing TIF file
                import rasterio
                with rasterio.open(tif_path) as src:
                    profile = src.profile.copy()
                    from rasterio.transform import array_bounds
                    profile['bounds'] = array_bounds(
                        profile['height'],
                        profile['width'],
                        profile['transform']
                    )
                
                write_metadata_doc(
                    os.path.dirname(tif_path),
                    location_name,
                    date,
                    items,
                    profile,
                    config
                )
                print(f"  ✓ Metadata updated!")
            except Exception as e:
                print(f"  ⚠ Could not generate metadata: {str(e)}")
            
            continue
        
        try:
            # Load, mosaic, and crop bands
            print(f"  Loading and mosaicking {len(items)} tile(s)...")
            rgb_array, profile = load_and_crop_bands(
                items,
                aoi_geometry,
                config['bands']
            )
            
            # Debug: Check raw data values
            print(f"  DEBUG - Raw data shape: {rgb_array.shape}")
            print(f"  DEBUG - Raw data type: {rgb_array.dtype}")
            print(f"  DEBUG - Raw data range: min={rgb_array.min()}, max={rgb_array.max()}")
            print(f"  DEBUG - Non-zero pixels: {np.count_nonzero(rgb_array)}/{rgb_array.size}")
            
            # Check for valid data
            if rgb_array.max() == 0:
                print(f"  ⚠ WARNING: All pixel values are zero! Skipping...")
                continue
            
            # Resample to target resolution
            print(f"  Checking resolution...")
            rgb_array, profile = resample_to_resolution(
                rgb_array,
                profile,
                config['output']['target_resolution']
            )
            
            # Print final image info
            width_m = profile['width'] * config['output']['target_resolution']
            height_m = profile['height'] * config['output']['target_resolution']
            print(f"  Final image: {profile['width']} x {profile['height']} pixels")
            print(f"  Coverage area: {width_m/1000:.2f} x {height_m/1000:.2f} km")
            
            # Debug: Check resampled data
            print(f"  DEBUG - Resampled data range: min={rgb_array.min()}, max={rgb_array.max()}")
            for i, band_name in enumerate(['Red', 'Green', 'Blue']):
                band = rgb_array[:, :, i]
                print(f"  DEBUG - {band_name} band: min={band.min()}, max={band.max()}, mean={band.mean():.2f}")
            
            # Export GeoTIFF
            print(f"  Exporting GeoTIFF...")
            export_geotiff(rgb_array, profile, tif_path)
            
            # Normalize for JPEG display (official Sentinel Hub method)
            print(f"  Normalizing for display...")
            rgb_normalized = normalize_for_display(rgb_array)
            
            # Debug: Check normalized data
            print(f"  DEBUG - Normalized data range: min={rgb_normalized.min()}, max={rgb_normalized.max()}")
            
            # Export JPEG
            print(f"  Exporting JPEG...")
            export_jpeg(
                rgb_normalized,
                jpg_path,
                quality=config['output']['jpg_quality']
            )
            
            # Write metadata documentation
            print(f"  Writing metadata documentation...")
            # Profile needs bounds for metadata
            if 'bounds' not in profile:
                from rasterio.transform import array_bounds
                profile['bounds'] = array_bounds(
                    profile['height'],
                    profile['width'],
                    profile['transform']
                )
            write_metadata_doc(
                os.path.dirname(tif_path),  # Use TIF directory (same as JPG)
                location_name,
                date,
                items,
                profile,
                config
            )
            
            print(f"  ✓ Successfully processed!")
            
        except Exception as e:
            print(f"  ✗ Error processing image: {str(e)}")
            import traceback
            traceback.print_exc()
            continue


# %%
# Process all shapefile-based AOIs
print("\n" + "=" * 80)
print("PROCESSING SHAPEFILE-BASED AOIs")
print("=" * 80)

if 'shapefile_aois' in config and config['shapefile_aois']:
    for aoi_config in config['shapefile_aois']:
        print(f"\n{'#'*80}")
        print(f"# Location: {aoi_config['location_name']}")
        print(f"{'#'*80}")
        
        # Load AOI from shapefile
        print(f"\nLoading AOI from shapefile...")
        print(f"  Path: {aoi_config['aoi_shapefile']}")
        
        aoi_gdf, aoi_geometry, bounds = load_aoi(aoi_config['aoi_shapefile'])
        print(f"  Features: {len(aoi_gdf)}")
        print(f"  Bounds: {bounds}")
        print(f"  CRS: {aoi_gdf.crs}")
        
        # Check if we should use bounding box instead of exact geometries
        use_bounding_box = aoi_config.get('use_bounding_box', False)
        if use_bounding_box and len(aoi_gdf) > 1:
            print(f"  Using full bounding box (not just feature geometries)")
            # Create a box from the bounds
            from shapely.geometry import box
            aoi_geometry = box(*bounds)
        
        # Check if we should process as single AOI or individual features
        process_as_single = aoi_config.get('process_as_single', True)
        
        if process_as_single or len(aoi_gdf) == 1:
            # Process all features as one unified AOI (default behavior)
            print(f"  Processing mode: Single unified AOI")
            
            process_aoi(
                location_name=aoi_config['location_name'],
                aoi_geometry=aoi_geometry,
                bounds=bounds,
                start_date=aoi_config['date_range']['start'],
                end_date=aoi_config['date_range']['end'],
                config=config
            )
        else:
            # Process each feature individually
            print(f"  Processing mode: Individual features ({len(aoi_gdf)} features)")
            id_field = aoi_config.get('id_field', 'fid')
            buffer_meters = aoi_config.get('buffer_meters', 0)
            shared_folder = aoi_config.get('shared_folder', False)
            
            # Check if id_field exists, otherwise use index
            if id_field not in aoi_gdf.columns:
                print(f"  Warning: ID field '{id_field}' not found, using index instead")
                use_index = True
            else:
                use_index = False
            
            if buffer_meters > 0:
                print(f"  Buffer: {buffer_meters}m around each feature")
            
            if shared_folder:
                print(f"  Output: All features in single folder '{aoi_config['location_name']}'")
            
            for idx, row in aoi_gdf.iterrows():
                # Get feature ID
                if use_index:
                    feature_id = idx + 1  # 1-based index
                else:
                    feature_id = row[id_field]
                
                # Create location name with feature ID
                location_name = f"{aoi_config['location_name']}_R{feature_id}"
                
                # Get geometry for this feature
                feature_geometry = row['geometry']
                
                # Apply buffer if specified (need to project to metric CRS first)
                if buffer_meters > 0:
                    # Get center for UTM zone calculation
                    centroid = feature_geometry.centroid
                    center_lon = centroid.x
                    center_lat = centroid.y
                    
                    # Determine UTM zone
                    utm_zone = int((center_lon + 180) / 6) + 1
                    hemisphere = 'north' if center_lat >= 0 else 'south'
                    utm_epsg = 32600 + utm_zone if hemisphere == 'north' else 32700 + utm_zone
                    
                    # Project to UTM, buffer, project back
                    from shapely.ops import transform
                    import pyproj
                    
                    wgs84_to_utm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True).transform
                    utm_to_wgs84 = pyproj.Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True).transform
                    
                    feature_utm = transform(wgs84_to_utm, feature_geometry)
                    buffered_utm = feature_utm.buffer(buffer_meters)
                    feature_geometry = transform(utm_to_wgs84, buffered_utm)
                
                feature_bounds = feature_geometry.bounds
                
                print(f"\n  [{idx+1}/{len(aoi_gdf)}] Processing feature {feature_id}...")
                print(f"    Location: {location_name}")
                if buffer_meters > 0:
                    print(f"    Original bounds (buffered by {buffer_meters}m)")
                print(f"    Bounds: {feature_bounds}")
                
                # Determine output folder
                output_folder = aoi_config['location_name'] if shared_folder else None
                
                # Process this individual feature
                process_aoi(
                    location_name=location_name,
                    aoi_geometry=feature_geometry,
                    bounds=feature_bounds,
                    start_date=aoi_config['date_range']['start'],
                    end_date=aoi_config['date_range']['end'],
                    config=config,
                    output_folder=output_folder
                )
else:
    print("  No shapefile AOIs configured.")


# %%
# Process all coordinate-based AOIs
print("\n" + "=" * 80)
print("PROCESSING COORDINATE-BASED AOIs")
print("=" * 80)

if 'coordinate_aois' in config and config['coordinate_aois'].get('coordinates'):
    coord_config = config['coordinate_aois']
    group_name = coord_config.get('location_group_name', 'Coordinate')
    square_size = coord_config['square_size_meters']
    
    print(f"\nCoordinate AOI settings:")
    print(f"  Group name: {group_name}")
    print(f"  Square size: {square_size}m x {square_size}m")
    
    # Calculate expected image size
    expected_pixels = square_size / config['output']['target_resolution']
    print(f"  Expected image size: ~{expected_pixels:.0f} x {expected_pixels:.0f} pixels")
    
    # Warn if too small
    if expected_pixels < 20:
        print(f"  ⚠️  WARNING: Square size is very small! Recommend at least 500m for good results.")
        print(f"             Current size will produce only {expected_pixels:.0f}x{expected_pixels:.0f} pixel images.")
    
    print(f"  Number of locations: {len(coord_config['coordinates'])}")
    print(f"  Date range: {coord_config['date_range']['start']} to {coord_config['date_range']['end']}")
    
    for idx, coords in enumerate(coord_config['coordinates'], 1):
        lat, lon = coords
        
        print(f"\n{'#'*80}")
        print(f"# Location {idx}/{len(coord_config['coordinates'])}: ({lat:.6f}, {lon:.6f})")
        print(f"{'#'*80}")
        
        # Create location name from coordinates
        # Format: GroupName_lat_lon (with underscores and limited precision)
        lat_str = f"{abs(lat):.4f}".replace('.', '_')
        lon_str = f"{abs(lon):.4f}".replace('.', '_')
        lat_dir = 'N' if lat >= 0 else 'S'
        lon_dir = 'E' if lon >= 0 else 'W'
        location_name = f"{group_name}_{lat_str}{lat_dir}_{lon_str}{lon_dir}"
        
        print(f"\nCreating square AOI...")
        print(f"  Center: {lat:.6f}, {lon:.6f}")
        print(f"  Size: {square_size}m x {square_size}m")
        
        try:
            aoi_gdf, aoi_geometry, bounds = create_square_aoi_from_coordinates(
                lat, lon, square_size
            )
            print(f"  Bounds: {bounds}")
            print(f"  CRS: {aoi_gdf.crs}")
            
            # Process this AOI
            process_aoi(
                location_name=location_name,
                aoi_geometry=aoi_geometry,
                bounds=bounds,
                start_date=coord_config['date_range']['start'],
                end_date=coord_config['date_range']['end'],
                config=config
            )
            
        except Exception as e:
            print(f"  ✗ Error creating/processing AOI: {str(e)}")
            import traceback
            traceback.print_exc()
            continue
else:
    print("  No coordinate AOIs configured.")


# %%
# Process overall bounding AOI for coordinate AOIs (e.g., Czechia_overall)
print("\n" + "=" * 80)
print("PROCESSING OVERALL BOUNDING AOI")
print("=" * 80)

if 'coordinate_aois' in config and config['coordinate_aois'].get('coordinates') and len(config['coordinate_aois']['coordinates']) > 1:
    coord_config = config['coordinate_aois']
    
    # Check if user wants to process overall AOI
    process_overall = coord_config.get('process_overall', True)
    
    if not process_overall:
        print("  Skipping overall AOI (disabled in config)")
    else:
        group_name = coord_config.get('location_group_name', 'Coordinate')
        
        print(f"\nCreating overall bounding AOI for {group_name}...")
        print(f"  Encompassing {len(coord_config['coordinates'])} individual locations")
        
        try:
            # Get buffer from config (default 500m)
            buffer_meters = coord_config.get('overall_buffer_meters', 500)
            
            aoi_gdf, aoi_geometry, bounds = create_overall_bounding_aoi(
                coord_config['coordinates'],
                coord_config['square_size_meters'],
                buffer_meters=buffer_meters
            )
            
            # Calculate coverage area
            from shapely.ops import transform
            import pyproj
            
            # Get center for UTM zone calculation
            center_lon = (bounds[0] + bounds[2]) / 2
            center_lat = (bounds[1] + bounds[3]) / 2
            utm_zone = int((center_lon + 180) / 6) + 1
            hemisphere = 'north' if center_lat >= 0 else 'south'
            utm_epsg = 32600 + utm_zone if hemisphere == 'north' else 32700 + utm_zone
            
            # Project to UTM to get area in km²
            project_to_utm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True).transform
            aoi_utm = transform(project_to_utm, aoi_geometry)
            area_km2 = aoi_utm.area / 1_000_000
            
            print(f"  Bounds (WGS84): {bounds}")
            print(f"  Total coverage area: {area_km2:.2f} km²")
            print(f"  Buffer: {buffer_meters}m")
            
            # Warn if AOI is very large
            if area_km2 > 1000:
                print(f"  ⚠️  WARNING: Large AOI ({area_km2:.0f} km²) may fail due to timeout/memory issues")
                print(f"             Consider reducing buffer_meters in config if processing fails")
                print(f"             Current buffer: {buffer_meters}m - try 100m or 0m if issues occur")
            
            # Process this overall AOI
            location_name = f"{group_name}_overall"
            
            process_aoi(
                location_name=location_name,
                aoi_geometry=aoi_geometry,
                bounds=bounds,
                start_date=coord_config['date_range']['start'],
                end_date=coord_config['date_range']['end'],
                config=config
            )
            
            print(f"\n✓ Successfully processed {group_name}_overall!")
            
        except Exception as e:
            print(f"\n  ✗ Error creating/processing overall AOI: {str(e)}")
            print(f"  This is often caused by:")
            print(f"    - Large AOI size causing timeout/memory issues")
            print(f"    - Network issues reading from cloud storage")
            print(f"    - Corrupted tiles in the data source")
            print(f"\n  💡 Solutions to try:")
            print(f"    1. Reduce overall_buffer_meters in config (currently {buffer_meters}m)")
            print(f"    2. Set process_overall: false to skip this step")
            print(f"    3. Try again later (transient cloud storage issues)")
            print(f"\n  Individual location images were still created successfully!")
            import traceback
            print(f"\n  Full error details:")
            traceback.print_exc()
else:
    print("  Skipping - need at least 2 coordinate AOIs for overall bounding AOI")


# %%
# Final summary
print("\n" + "=" * 80)
print("PROCESSING COMPLETE!")
print("=" * 80)
print("\n📊 Summary:")
print(f"  Output directory: {config['output']['base_dir']}/")
print(f"  GeoTIFF files: {config['output']['tif_subdir']}/")
print(f"  JPEG files: {config['output']['jpg_subdir']}/")
print(f"  True color method: Official Sentinel Hub (linear gain)")


# %%
