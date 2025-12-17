"""Tests for the converter module."""

import json
import pytest

from mapbox_tileset_uploader.converter import convert_topojson_to_geojson


class TestTopoJSONConverter:
    """Test TopoJSON to GeoJSON conversion."""

    def test_simple_polygon(self) -> None:
        """Test converting a simple polygon."""
        topojson = {
            "type": "Topology",
            "objects": {
                "test": {
                    "type": "GeometryCollection",
                    "geometries": [
                        {
                            "type": "Polygon",
                            "arcs": [[0]],
                            "properties": {"name": "Test"},
                        }
                    ],
                }
            },
            "arcs": [[[0, 0], [1, 0], [0, 1], [-1, 0], [0, -1]]],
        }

        geojson = convert_topojson_to_geojson(topojson)

        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        assert geojson["features"][0]["properties"]["name"] == "Test"
        assert geojson["features"][0]["geometry"]["type"] == "Polygon"

    def test_with_transform(self) -> None:
        """Test converting with quantization transform."""
        topojson = {
            "type": "Topology",
            "transform": {"scale": [0.001, 0.001], "translate": [-180, -90]},
            "objects": {
                "test": {
                    "type": "GeometryCollection",
                    "geometries": [
                        {
                            "type": "Point",
                            "coordinates": [180000, 90000],
                            "properties": {"name": "Origin"},
                        }
                    ],
                }
            },
            "arcs": [],
        }

        geojson = convert_topojson_to_geojson(topojson)

        assert geojson["type"] == "FeatureCollection"
        coords = geojson["features"][0]["geometry"]["coordinates"]
        assert coords[0] == pytest.approx(0.0, abs=0.01)  # -180 + 180000 * 0.001
        assert coords[1] == pytest.approx(0.0, abs=0.01)  # -90 + 90000 * 0.001

    def test_invalid_topology(self) -> None:
        """Test that invalid TopoJSON raises error."""
        with pytest.raises(ValueError, match="not a valid TopoJSON"):
            convert_topojson_to_geojson({"type": "FeatureCollection"})

    def test_empty_objects(self) -> None:
        """Test that empty objects raise error."""
        with pytest.raises(ValueError, match="no objects"):
            convert_topojson_to_geojson({"type": "Topology", "objects": {}})

    def test_specific_object_name(self) -> None:
        """Test selecting a specific object by name."""
        topojson = {
            "type": "Topology",
            "objects": {
                "countries": {
                    "type": "GeometryCollection",
                    "geometries": [{"type": "Point", "coordinates": [0, 0], "properties": {"name": "Country"}}],
                },
                "cities": {
                    "type": "GeometryCollection",
                    "geometries": [{"type": "Point", "coordinates": [1, 1], "properties": {"name": "City"}}],
                },
            },
            "arcs": [],
        }

        geojson = convert_topojson_to_geojson(topojson, object_name="cities")

        assert geojson["features"][0]["properties"]["name"] == "City"

    def test_object_not_found(self) -> None:
        """Test error when object name not found."""
        topojson = {
            "type": "Topology",
            "objects": {"test": {"type": "GeometryCollection", "geometries": []}},
            "arcs": [],
        }

        with pytest.raises(ValueError, match="not found"):
            convert_topojson_to_geojson(topojson, object_name="nonexistent")


class TestGeometryTypes:
    """Test various geometry types."""

    def test_multipolygon(self) -> None:
        """Test MultiPolygon conversion."""
        topojson = {
            "type": "Topology",
            "objects": {
                "test": {
                    "type": "GeometryCollection",
                    "geometries": [
                        {
                            "type": "MultiPolygon",
                            "arcs": [[[0]], [[1]]],
                            "properties": {},
                        }
                    ],
                }
            },
            "arcs": [
                [[0, 0], [1, 0], [0, 1], [-1, 0], [0, -1]],
                [[2, 0], [1, 0], [0, 1], [-1, 0], [0, -1]],
            ],
        }

        geojson = convert_topojson_to_geojson(topojson)

        assert geojson["features"][0]["geometry"]["type"] == "MultiPolygon"
        assert len(geojson["features"][0]["geometry"]["coordinates"]) == 2

    def test_linestring(self) -> None:
        """Test LineString conversion."""
        topojson = {
            "type": "Topology",
            "objects": {
                "test": {
                    "type": "GeometryCollection",
                    "geometries": [{"type": "LineString", "arcs": [0], "properties": {}}],
                }
            },
            "arcs": [[[0, 0], [1, 0], [1, 1]]],
        }

        geojson = convert_topojson_to_geojson(topojson)

        assert geojson["features"][0]["geometry"]["type"] == "LineString"
