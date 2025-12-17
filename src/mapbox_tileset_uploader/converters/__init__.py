"""
Converters package for transforming various GIS formats to GeoJSON.

Supported formats:
- GeoJSON (.geojson, .json) - native
- TopoJSON (.topojson) - built-in converter
- Shapefile (.shp) - requires pyshp or fiona
- GeoPackage (.gpkg) - requires fiona
- KML/KMZ (.kml, .kmz) - requires fiona or fastkml
- FlatGeobuf (.fgb) - requires fiona
- GeoParquet (.parquet, .geoparquet) - requires geopandas
- GML (.gml) - requires fiona
- GPX (.gpx) - requires gpxpy
"""

from mapbox_tileset_uploader.converters.base import BaseConverter, ConversionResult
from mapbox_tileset_uploader.converters.registry import (
    ConverterRegistry,
    get_converter,
    get_supported_formats,
    register_converter,
)

__all__ = [
    "BaseConverter",
    "ConversionResult",
    "ConverterRegistry",
    "get_converter",
    "get_supported_formats",
    "register_converter",
]
