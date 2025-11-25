"""Functions for handling AOI from shapefile and coordinates."""

import geopandas as gpd
from shapely.geometry import box, Point
import pyproj
from pyproj import Transformer


def load_aoi(shapefile_path):
    """Load AOI from shapefile and return geometry and bounds.
    
    Args:
        shapefile_path: Path to shapefile
        
    Returns:
        tuple: (GeoDataFrame, unified geometry, bounds)
    """
    gdf = gpd.read_file(shapefile_path)
    
    # Reproject to WGS84 if needed
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    
    # Unary union to get single geometry
    aoi_geometry = gdf.unary_union
    
    # Get bounds (minx, miny, maxx, maxy)
    bounds = aoi_geometry.bounds
    
    return gdf, aoi_geometry, bounds


def create_square_aoi_from_coordinates(lat, lon, square_size_meters):
    """Create a square AOI around a coordinate point.
    
    Args:
        lat: Latitude in WGS84 (EPSG:4326)
        lon: Longitude in WGS84 (EPSG:4326)
        square_size_meters: Side length of square in meters
        
    Returns:
        tuple: (GeoDataFrame, geometry, bounds) - all in WGS84
    """
    # Create point in WGS84
    point_wgs84 = Point(lon, lat)
    
    # Project to UTM for accurate distance measurements
    # Determine appropriate UTM zone from longitude
    utm_zone = int((lon + 180) / 6) + 1
    hemisphere = 'north' if lat >= 0 else 'south'
    utm_epsg = 32600 + utm_zone if hemisphere == 'north' else 32700 + utm_zone
    
    # Create transformers
    wgs84_to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    utm_to_wgs84 = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
    
    # Transform point to UTM
    x_utm, y_utm = wgs84_to_utm.transform(lon, lat)
    
    # Create square in UTM (centered on point)
    half_size = square_size_meters / 2.0
    minx = x_utm - half_size
    maxx = x_utm + half_size
    miny = y_utm - half_size
    maxy = y_utm + half_size
    
    square_utm = box(minx, miny, maxx, maxy)
    
    # Transform back to WGS84
    # Get coordinates of the square and transform each
    coords = list(square_utm.exterior.coords)
    coords_wgs84 = [utm_to_wgs84.transform(x, y) for x, y in coords]
    
    # Create polygon in WGS84
    from shapely.geometry import Polygon
    square_wgs84 = Polygon(coords_wgs84)
    
    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame([{'geometry': square_wgs84}], crs="EPSG:4326")
    
    # Get bounds
    bounds = square_wgs84.bounds
    
    return gdf, square_wgs84, bounds


def create_overall_bounding_aoi(coordinates, square_size_meters, buffer_meters=0):
    """Create an overall AOI that encompasses all coordinate points.
    
    Args:
        coordinates: List of [lat, lon] coordinate pairs
        square_size_meters: Size of individual squares (used for buffering)
        buffer_meters: Additional buffer around the overall bounds (default: 0)
        
    Returns:
        tuple: (GeoDataFrame, geometry, bounds) - all in WGS84
    """
    if not coordinates or len(coordinates) == 0:
        raise ValueError("Need at least one coordinate")
    
    # Create all individual squares and collect their bounds
    all_bounds = []
    
    for lat, lon in coordinates:
        _, _, bounds = create_square_aoi_from_coordinates(lat, lon, square_size_meters)
        all_bounds.append(bounds)
    
    # Find overall min/max in WGS84
    all_minx = [b[0] for b in all_bounds]
    all_miny = [b[1] for b in all_bounds]
    all_maxx = [b[2] for b in all_bounds]
    all_maxy = [b[3] for b in all_bounds]
    
    overall_minx = min(all_minx)
    overall_miny = min(all_miny)
    overall_maxx = max(all_maxx)
    overall_maxy = max(all_maxy)
    
    # Apply buffer if requested (need to convert to meters)
    if buffer_meters > 0:
        # Use UTM for accurate buffering
        # Determine UTM zone from center point
        center_lon = (overall_minx + overall_maxx) / 2
        center_lat = (overall_miny + overall_maxy) / 2
        
        utm_zone = int((center_lon + 180) / 6) + 1
        hemisphere = 'north' if center_lat >= 0 else 'south'
        utm_epsg = 32600 + utm_zone if hemisphere == 'north' else 32700 + utm_zone
        
        # Transform bounds to UTM
        wgs84_to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        utm_to_wgs84 = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
        
        # Transform corners
        minx_utm, miny_utm = wgs84_to_utm.transform(overall_minx, overall_miny)
        maxx_utm, maxy_utm = wgs84_to_utm.transform(overall_maxx, overall_maxy)
        
        # Apply buffer in UTM
        minx_utm -= buffer_meters
        miny_utm -= buffer_meters
        maxx_utm += buffer_meters
        maxy_utm += buffer_meters
        
        # Transform back to WGS84
        overall_minx, overall_miny = utm_to_wgs84.transform(minx_utm, miny_utm)
        overall_maxx, overall_maxy = utm_to_wgs84.transform(maxx_utm, maxy_utm)
    
    # Create bounding box
    bbox = box(overall_minx, overall_miny, overall_maxx, overall_maxy)
    
    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame([{'geometry': bbox}], crs="EPSG:4326")
    
    # Get bounds
    bounds = bbox.bounds
    
    return gdf, bbox, bounds


def check_coverage(aoi_geometry, image_geometry):
    """Check if image fully covers the AOI.
    
    Args:
        aoi_geometry: Shapely geometry of AOI
        image_geometry: Shapely geometry of image footprint
        
    Returns:
        tuple: (coverage_percentage, is_fully_covered)
    """
    if not image_geometry.intersects(aoi_geometry):
        return 0.0, False
    
    intersection = image_geometry.intersection(aoi_geometry)
    coverage_pct = (intersection.area / aoi_geometry.area) * 100
    
    return coverage_pct, coverage_pct >= 99.9  # Allow small rounding errors

