"""Functions for querying Sentinel-2 data."""

import pystac_client
import planetary_computer
from shapely.geometry import shape
from shapely.ops import unary_union
from collections import defaultdict


def search_sentinel2_images(bounds, start_date, end_date, max_cloud_cover, aoi_geometry):
    """Search for Sentinel-2 images that cover the AOI, grouped by date.
    
    Args:
        bounds: Bounding box (minx, miny, maxx, maxy)
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        max_cloud_cover: Maximum cloud cover percentage
        aoi_geometry: Shapely geometry for coverage check
        
    Returns:
        dict: Dictionary with dates as keys and list of STAC items as values
    """
    from src.aoi_handler import check_coverage
    
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    
    bbox = [bounds[0], bounds[1], bounds[2], bounds[3]]
    
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{start_date}/{end_date}",
        query={"eo:cloud_cover": {"lt": max_cloud_cover}}
    )
    
    items = list(search.items())
    print(f"Found {len(items)} Sentinel-2 tiles with cloud cover < {max_cloud_cover}%")
    
    # Group items by date
    items_by_date = defaultdict(list)
    for item in items:
        date_str = item.properties.get('datetime', '')[:10]
        items_by_date[date_str].append(item)
    
    print(f"\nGrouped into {len(items_by_date)} unique dates")
    
    # Check coverage for merged tiles per date
    fully_covered_dates = {}
    for date, date_items in sorted(items_by_date.items()):
        # Merge geometries of all tiles for this date
        merged_geom = unary_union([shape(item.geometry) for item in date_items])
        coverage_pct, is_covered = check_coverage(aoi_geometry, merged_geom)
        
        avg_cloud = sum(item.properties.get('eo:cloud_cover', 0) for item in date_items) / len(date_items)
        
        if is_covered:
            fully_covered_dates[date] = date_items
            print(f"  ✓ {date} - {len(date_items)} tiles - Avg cloud: {avg_cloud:.1f}% - Coverage: {coverage_pct:.1f}%")
        else:
            print(f"  ✗ {date} - {len(date_items)} tiles - Incomplete coverage: {coverage_pct:.1f}%")
    
    print(f"\nTotal dates with full AOI coverage: {len(fully_covered_dates)}")
    
    return fully_covered_dates

