"""
Converter module for transforming TopoJSON to GeoJSON.
"""

import json
from typing import Any, Dict, List, Union


def convert_topojson_to_geojson(
    topojson: Dict[str, Any],
    object_name: str | None = None,
) -> Dict[str, Any]:
    """
    Convert TopoJSON to GeoJSON.

    Args:
        topojson: TopoJSON data as a dictionary
        object_name: Name of the object to convert. If None, converts the first object.

    Returns:
        GeoJSON FeatureCollection
    """
    if topojson.get("type") != "Topology":
        raise ValueError("Input is not a valid TopoJSON (missing 'Topology' type)")

    objects = topojson.get("objects", {})
    if not objects:
        raise ValueError("TopoJSON contains no objects")

    # Get the object to convert
    if object_name:
        if object_name not in objects:
            raise ValueError(f"Object '{object_name}' not found in TopoJSON")
        obj = objects[object_name]
    else:
        # Use the first object
        object_name = next(iter(objects))
        obj = objects[object_name]

    arcs = topojson.get("arcs", [])
    transform = topojson.get("transform")

    features = []
    geometries = obj.get("geometries", [obj])

    for geometry in geometries:
        feature = {
            "type": "Feature",
            "properties": geometry.get("properties", {}),
            "geometry": _decode_geometry(geometry, arcs, transform),
        }
        if "id" in geometry:
            feature["id"] = geometry["id"]
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def _decode_geometry(
    geometry: Dict[str, Any],
    arcs: List[List[List[int]]],
    transform: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """Decode a TopoJSON geometry to GeoJSON geometry."""
    geom_type = geometry.get("type")

    if geom_type is None or geom_type == "null":
        return None

    if geom_type == "Point":
        coords = geometry.get("coordinates", [])
        return {"type": "Point", "coordinates": _transform_point(coords, transform)}

    if geom_type == "MultiPoint":
        coords = geometry.get("coordinates", [])
        return {
            "type": "MultiPoint",
            "coordinates": [_transform_point(c, transform) for c in coords],
        }

    if geom_type == "LineString":
        arc_indices = geometry.get("arcs", [])
        return {
            "type": "LineString",
            "coordinates": _decode_arcs(arc_indices, arcs, transform),
        }

    if geom_type == "MultiLineString":
        arc_groups = geometry.get("arcs", [])
        return {
            "type": "MultiLineString",
            "coordinates": [_decode_arcs(ag, arcs, transform) for ag in arc_groups],
        }

    if geom_type == "Polygon":
        arc_groups = geometry.get("arcs", [])
        return {
            "type": "Polygon",
            "coordinates": [_decode_arcs(ring, arcs, transform) for ring in arc_groups],
        }

    if geom_type == "MultiPolygon":
        polygon_groups = geometry.get("arcs", [])
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [_decode_arcs(ring, arcs, transform) for ring in polygon]
                for polygon in polygon_groups
            ],
        }

    if geom_type == "GeometryCollection":
        geometries = geometry.get("geometries", [])
        return {
            "type": "GeometryCollection",
            "geometries": [_decode_geometry(g, arcs, transform) for g in geometries],
        }

    raise ValueError(f"Unknown geometry type: {geom_type}")


def _decode_arcs(
    arc_indices: List[int],
    arcs: List[List[List[int]]],
    transform: Dict[str, Any] | None,
) -> List[List[float]]:
    """Decode arc indices to coordinates."""
    coordinates: List[List[float]] = []

    for arc_index in arc_indices:
        # Handle negative indices (reversed arcs)
        if arc_index < 0:
            arc = list(reversed(arcs[~arc_index]))
        else:
            arc = arcs[arc_index]

        # Decode delta-encoded coordinates
        decoded_arc = _decode_arc(arc, transform)

        # Skip first point if not the first arc (to avoid duplicates)
        start = 0 if not coordinates else 1
        coordinates.extend(decoded_arc[start:])

    return coordinates


def _decode_arc(
    arc: List[List[int]],
    transform: Dict[str, Any] | None,
) -> List[List[float]]:
    """Decode a single arc with delta encoding and optional transform."""
    coordinates: List[List[float]] = []
    x, y = 0, 0

    for point in arc:
        x += point[0]
        y += point[1]
        coordinates.append(_transform_point([x, y], transform))

    return coordinates


def _transform_point(
    point: List[Union[int, float]],
    transform: Dict[str, Any] | None,
) -> List[float]:
    """Apply transform to a point."""
    if transform is None:
        return [float(point[0]), float(point[1])]

    scale = transform.get("scale", [1, 1])
    translate = transform.get("translate", [0, 0])

    return [
        point[0] * scale[0] + translate[0],
        point[1] * scale[1] + translate[1],
    ]


def load_and_convert(
    file_path: str,
    object_name: str | None = None,
) -> Dict[str, Any]:
    """
    Load a TopoJSON file and convert it to GeoJSON.

    Args:
        file_path: Path to the TopoJSON file
        object_name: Name of the object to convert

    Returns:
        GeoJSON FeatureCollection
    """
    with open(file_path, "r", encoding="utf-8") as f:
        topojson = json.load(f)
    return convert_topojson_to_geojson(topojson, object_name)
