"""
Mapbox Tileset Uploader - Upload GIS data to Mapbox as vector tilesets.

Supports multiple formats:
- GeoJSON (.geojson, .json)
- TopoJSON (.topojson)
- Shapefile (.shp, .zip)
- GeoPackage (.gpkg)
- KML/KMZ (.kml, .kmz)
- FlatGeobuf (.fgb)
- GeoParquet (.parquet, .geoparquet)
- GPX (.gpx)
"""

from mapbox_tileset_uploader.converters import (
    BaseConverter,
    ConversionResult,
    get_converter,
    get_supported_formats,
)
from mapbox_tileset_uploader.uploader import (
    TilesetConfig,
    TilesetUploader,
    UploadResult,
)
from mapbox_tileset_uploader.validators import (
    GeometryValidator,
    ValidationResult,
    ValidationWarning,
    validate_geojson,
)

__version__ = "0.2.0"
__all__ = [
    # Core
    "TilesetUploader",
    "TilesetConfig",
    "UploadResult",
    # Converters
    "get_converter",
    "get_supported_formats",
    "BaseConverter",
    "ConversionResult",
    # Validators
    "GeometryValidator",
    "ValidationResult",
    "ValidationWarning",
    "validate_geojson",
    # Version
    "__version__",
]
