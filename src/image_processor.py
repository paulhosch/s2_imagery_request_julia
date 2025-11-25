"""Functions for processing and exporting Sentinel-2 images."""

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from PIL import Image
import planetary_computer
import time
from rasterio.errors import RasterioIOError


def load_and_crop_bands(items, aoi_geometry, bands_config, max_retries=3):
    """Load RGB bands from multiple tiles, mosaic, and crop to AOI.
    
    Args:
        items: List of STAC items (tiles for the same date)
        aoi_geometry: Shapely geometry of AOI (in WGS84)
        bands_config: Dictionary with 'red', 'green', 'blue' band names
        max_retries: Maximum number of retry attempts for failed reads
        
    Returns:
        tuple: (rgb_array, profile) - RGB array (H, W, 3) and rasterio profile
    """
    import pyproj
    from shapely.ops import transform
    
    # Process each band separately
    rgb_bands = []
    
    for band_name in ['red', 'green', 'blue']:
        band_key = bands_config[band_name]
        
        # Open all tiles for this band with retry logic
        src_files = []
        for item in items:
            band_href = planetary_computer.sign(item.assets[band_key].href)
            
            # Try to open with retries
            for attempt in range(max_retries):
                try:
                    src = rasterio.open(band_href)
                    src_files.append(src)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"    Retry {attempt + 1}/{max_retries} for {band_name} band...")
                        time.sleep(2)  # Wait before retry
                    else:
                        raise Exception(f"Failed to open {band_name} band after {max_retries} attempts: {str(e)}")
        
        # Determine target CRS from first source
        target_crs = src_files[0].crs
        
        # Reproject AOI geometry to target CRS
        project = pyproj.Transformer.from_crs(
            "EPSG:4326",  # WGS84 (AOI is in this CRS)
            target_crs,
            always_xy=True
        ).transform
        aoi_reprojected = transform(project, aoi_geometry)
        
        # Mosaic tiles if multiple, otherwise use single tile
        if len(src_files) > 1:
            # Check for CRS mismatch and reproject if needed
            crs_mismatch = any(src.crs != target_crs for src in src_files)
            
            if crs_mismatch:
                print(f"    Reprojecting tiles to common CRS: {target_crs}")
                # Reproject all files to the first file's CRS
                from rasterio.io import MemoryFile
                reprojected_files = []
                
                for src in src_files:
                    if src.crs != target_crs:
                        # Calculate transform for reprojection
                        transform_calc, width, height = calculate_default_transform(
                            src.crs, target_crs, src.width, src.height, *src.bounds
                        )
                        
                        # Create in-memory reprojected dataset
                        memfile = MemoryFile()
                        reproj_profile = src.profile.copy()
                        reproj_profile.update({
                            'crs': target_crs,
                            'transform': transform_calc,
                            'width': width,
                            'height': height
                        })
                        
                        mem_dataset = memfile.open(**reproj_profile)
                        
                        # Reproject
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=rasterio.band(mem_dataset, 1),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=transform_calc,
                            dst_crs=target_crs,
                            resampling=Resampling.bilinear
                        )
                        
                        reprojected_files.append(mem_dataset)
                    else:
                        reprojected_files.append(src)
                
                # Merge reprojected files
                mosaic_array, mosaic_transform = merge(reprojected_files)
                
                # Close memory files
                for rf in reprojected_files:
                    if rf not in src_files:
                        rf.close()
            else:
                # All same CRS, merge directly
                mosaic_array, mosaic_transform = merge(src_files)
            
            # Create in-memory dataset for the mosaic
            profile = src_files[0].profile.copy()
            profile.update({
                'crs': target_crs,
                'height': mosaic_array.shape[1],
                'width': mosaic_array.shape[2],
                'transform': mosaic_transform
            })
            
            # Use rasterio MemoryFile to create temporary dataset
            from rasterio.io import MemoryFile
            with MemoryFile() as memfile:
                with memfile.open(**profile) as mem_dataset:
                    mem_dataset.write(mosaic_array)
                    # Crop to AOI (using reprojected geometry)
                    cropped, out_transform = mask(mem_dataset, [aoi_reprojected], crop=True)
        else:
            # Single tile - just crop (using reprojected geometry) with retry logic
            for attempt in range(max_retries):
                try:
                    cropped, out_transform = mask(src_files[0], [aoi_reprojected], crop=True)
                    break
                except (RasterioIOError, Exception) as e:
                    if attempt < max_retries - 1:
                        print(f"    Retry {attempt + 1}/{max_retries} for cropping {band_name} band...")
                        time.sleep(3)  # Wait longer before retry
                        # Re-sign and re-open the URL
                        for src in src_files:
                            src.close()
                        src_files = []
                        for item in items:
                            band_href = planetary_computer.sign(item.assets[band_key].href)
                            src_files.append(rasterio.open(band_href))
                    else:
                        raise Exception(f"Failed to crop {band_name} band after {max_retries} attempts: {str(e)}")
            
            profile = src_files[0].profile.copy()
        
        # Close all source files
        for src in src_files:
            src.close()
        
        rgb_bands.append(cropped[0])
    
    # Stack bands
    rgb = np.stack(rgb_bands, axis=-1)
    
    # Update profile
    profile.update({
        'driver': 'GTiff',
        'count': 3,
        'height': rgb.shape[0],
        'width': rgb.shape[1],
        'transform': out_transform,
        'compress': 'lzw'
    })
    
    return rgb, profile


def resample_to_resolution(rgb_array, profile, target_resolution):
    """Resample RGB array to target resolution.
    
    Args:
        rgb_array: RGB array (H, W, 3)
        profile: Rasterio profile with current transform
        target_resolution: Target resolution in meters/pixel
        
    Returns:
        tuple: (resampled_rgb_array, updated_profile)
    """
    # Get current resolution from transform
    current_resolution = profile['transform'][0]
    
    # Check if resampling is needed
    if abs(current_resolution - target_resolution) < 0.01:
        print(f"    Already at target resolution {target_resolution}m/px")
        return rgb_array, profile
    
    # Calculate new dimensions
    scale_factor = current_resolution / target_resolution
    new_height = int(profile['height'] * scale_factor)
    new_width = int(profile['width'] * scale_factor)
    
    print(f"    Resampling from {current_resolution:.1f}m/px to {target_resolution}m/px")
    print(f"    New dimensions: {new_width} x {new_height} pixels")
    
    # Calculate new transform
    transform = profile['transform']
    new_transform = rasterio.Affine(
        target_resolution, transform.b, transform.c,
        transform.d, -target_resolution, transform.f
    )
    
    # Prepare output array
    resampled_rgb = np.zeros((new_height, new_width, 3), dtype=rgb_array.dtype)
    
    # Resample each band
    for i in range(3):
        reproject(
            source=rgb_array[:, :, i],
            destination=resampled_rgb[:, :, i],
            src_transform=transform,
            src_crs=profile['crs'],
            dst_transform=new_transform,
            dst_crs=profile['crs'],
            resampling=Resampling.bilinear
        )
    
    # Update profile
    updated_profile = profile.copy()
    updated_profile.update({
        'height': new_height,
        'width': new_width,
        'transform': new_transform
    })
    
    return resampled_rgb, updated_profile


def normalize_for_display(rgb_array, gain=2.5):
    """Normalize RGB array for display using the official Sentinel Hub method.
    
    This matches the Sentinel Hub true color script which simply applies
    a linear gain to the reflectance values for consistent, comparable
    true color visualization across all images.
    
    Official Sentinel Hub approach:
        reflectance = pixel_value / 10000.0
        output = reflectance * gain
    
    Args:
        rgb_array: RGB array (H, W, 3) - Sentinel-2 L2A values (0-10000 range)
        gain: Linear gain multiplier (default 2.5, same as official script)
              Adjust if images are too dark (increase) or too bright (decrease)
        
    Returns:
        numpy.ndarray: Normalized RGB array (H, W, 3) with values 0-255 uint8
    """
    rgb_normalized = np.zeros_like(rgb_array, dtype=np.uint8)
    
    for i in range(3):
        band = rgb_array[:, :, i].astype(float)
        
        # Convert to reflectance (0-1 range) and apply gain
        # Sentinel-2 L2A reflectance values are scaled by 10000
        reflectance = (band / 10000.0) * gain
        
        # Clip to valid range and convert to 8-bit
        reflectance_clipped = np.clip(reflectance, 0, 1)
        rgb_normalized[:, :, i] = (reflectance_clipped * 255).astype(np.uint8)
    
    return rgb_normalized


def export_geotiff(rgb_array, profile, output_path):
    """Export RGB array as GeoTIFF.
    
    Args:
        rgb_array: RGB array (H, W, 3)
        profile: Rasterio profile
        output_path: Output file path
    """
    with rasterio.open(output_path, 'w', **profile) as dst:
        for i in range(3):
            dst.write(rgb_array[:, :, i], i + 1)
    
    print(f"Saved GeoTIFF: {output_path}")


def export_jpeg(rgb_array, output_path, quality=95):
    """Export RGB array as JPEG.
    
    Args:
        rgb_array: RGB array (H, W, 3) with values 0-255
        output_path: Output file path
        quality: JPEG quality (0-100)
    """
    img = Image.fromarray(rgb_array)
    img.save(output_path, 'JPEG', quality=quality)
    
    print(f"Saved JPEG: {output_path}")


def write_metadata_doc(output_dir, location_name, date, items, profile, config):
    """Write metadata documentation file for the image.
    
    Args:
        output_dir: Directory to write doc.txt (same as image location)
        location_name: Name of the location
        date: Acquisition date (YYYY-MM-DD)
        items: List of STAC items used to create the image
        profile: Rasterio profile with CRS and transform info
        config: Configuration dictionary
    """
    import os
    from datetime import datetime
    
    doc_path = os.path.join(output_dir, 'doc.txt')
    
    with open(doc_path, 'w') as f:
        f.write("=" * 70 + "\n")
        f.write("SENTINEL-2 TRUE COLOR IMAGE METADATA\n")
        f.write("=" * 70 + "\n\n")
        
        # Basic Information
        f.write(f"Location: {location_name}\n")
        f.write(f"Acquisition Date: {date}\n")
        f.write(f"Processing Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Number of Tiles: {len(items)}\n\n")
        
        # Projection Information
        f.write("-" * 70 + "\n")
        f.write("PROJECTION & COORDINATE SYSTEM\n")
        f.write("-" * 70 + "\n")
        crs_epsg = profile['crs'].to_epsg() if profile['crs'].to_epsg() else "N/A"
        f.write(f"Projection: {profile['crs']}\n")
        f.write(f"EPSG Code: {crs_epsg}\n")
        f.write(f"Linear Units: {profile['crs'].linear_units}\n\n")
        
        # Image Properties
        f.write("-" * 70 + "\n")
        f.write("IMAGE PROPERTIES\n")
        f.write("-" * 70 + "\n")
        f.write(f"Width: {profile['width']} pixels\n")
        f.write(f"Height: {profile['height']} pixels\n")
        f.write(f"Resolution: {config['output']['target_resolution']}m/pixel\n")
        f.write(f"Bands: RGB (Red: B04, Green: B03, Blue: B02)\n")
        f.write(f"Data Type: {profile['dtype']}\n\n")
        
        # Coverage Area
        width_m = profile['width'] * config['output']['target_resolution']
        height_m = profile['height'] * config['output']['target_resolution']
        area_km2 = (width_m * height_m) / 1_000_000
        f.write(f"Coverage: {width_m/1000:.3f} km × {height_m/1000:.3f} km\n")
        f.write(f"Total Area: {area_km2:.3f} km²\n\n")
        
        # Geotransform
        transform = profile['transform']
        f.write("-" * 70 + "\n")
        f.write("GEOTRANSFORM\n")
        f.write("-" * 70 + "\n")
        f.write(f"Origin X: {transform.c:.2f}\n")
        f.write(f"Origin Y: {transform.f:.2f}\n")
        f.write(f"Pixel Width: {transform.a:.2f}\n")
        f.write(f"Pixel Height: {-transform.e:.2f}\n")
        f.write(f"Rotation: {transform.b:.2f}, {transform.d:.2f}\n\n")
        
        # Bounds
        bounds = profile.get('bounds')
        if bounds:
            f.write(f"Bounds:\n")
            f.write(f"  West: {bounds[0]:.2f}\n")
            f.write(f"  South: {bounds[1]:.2f}\n")
            f.write(f"  East: {bounds[2]:.2f}\n")
            f.write(f"  North: {bounds[3]:.2f}\n\n")
        
        # Sentinel-2 Tile Information
        f.write("-" * 70 + "\n")
        f.write("SENTINEL-2 TILE INFORMATION\n")
        f.write("-" * 70 + "\n")
        
        for idx, item in enumerate(items, 1):
            f.write(f"\nTile {idx}:\n")
            
            # Product ID
            product_id = item.id
            f.write(f"  Product ID: {product_id}\n")
            
            # Datetime
            item_datetime = item.properties.get('datetime', 'N/A')
            f.write(f"  Acquisition Time: {item_datetime}\n")
            
            # Platform
            platform = item.properties.get('platform', 'N/A')
            f.write(f"  Satellite: {platform.upper() if platform != 'N/A' else 'N/A'}\n")
            
            # Orbit properties
            orbit_state = item.properties.get('sat:orbit_state', 'N/A')
            relative_orbit = item.properties.get('sat:relative_orbit', 'N/A')
            f.write(f"  Orbit Direction: {orbit_state}\n")
            f.write(f"  Relative Orbit: {relative_orbit}\n")
            
            # Cloud cover
            cloud_cover = item.properties.get('eo:cloud_cover', 'N/A')
            if cloud_cover != 'N/A':
                f.write(f"  Cloud Cover: {cloud_cover:.2f}%\n")
            else:
                f.write(f"  Cloud Cover: N/A\n")
            
            # Processing level
            processing_level = item.properties.get('s2:processing_baseline', 'N/A')
            f.write(f"  Processing Baseline: {processing_level}\n")
            
            # MGRS tile
            mgrs_tile = item.properties.get('s2:mgrs_tile', 'N/A')
            f.write(f"  MGRS Tile: {mgrs_tile}\n")
        
        # Processing Information
        f.write("\n" + "-" * 70 + "\n")
        f.write("PROCESSING INFORMATION\n")
        f.write("-" * 70 + "\n")
        f.write(f"Normalization Method: Official Sentinel Hub (linear gain)\n")
        f.write(f"Gain Factor: 2.5\n")
        f.write(f"Compression (GeoTIFF): LZW\n")
        f.write(f"JPEG Quality: {config['output']['jpg_quality']}\n")
        f.write(f"Max Cloud Cover Filter: {config['sentinel2']['max_cloud_cover']}%\n")
        f.write(f"Min AOI Coverage: {config['sentinel2']['min_aoi_coverage']}%\n\n")
        
        f.write("=" * 70 + "\n")
        f.write("End of Metadata\n")
        f.write("=" * 70 + "\n")
    
    print(f"  Saved metadata: {doc_path}")

