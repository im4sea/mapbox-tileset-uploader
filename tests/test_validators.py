"""Tests for the validators module."""

from mapbox_tileset_uploader.validators import (
    GeometryValidator,
    ValidationResult,
    ValidationWarning,
    validate_geojson,
)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_warning_count(self) -> None:
        """Test warning count property."""
        result = ValidationResult(
            valid=True,
            warnings=[
                ValidationWarning(None, None, "test", "msg", severity="warning"),
                ValidationWarning(None, None, "test", "msg", severity="warning"),
                ValidationWarning(None, None, "test", "msg", severity="info"),
            ],
            feature_count=1,
            valid_feature_count=1,
        )
        assert result.warning_count == 2

    def test_error_count(self) -> None:
        """Test error count property."""
        result = ValidationResult(
            valid=False,
            warnings=[
                ValidationWarning(None, None, "test", "msg", severity="error"),
                ValidationWarning(None, None, "test", "msg", severity="warning"),
            ],
            feature_count=1,
            valid_feature_count=0,
        )
        assert result.error_count == 1

    def test_get_warnings_by_type(self) -> None:
        """Test filtering warnings by type."""
        result = ValidationResult(
            valid=True,
            warnings=[
                ValidationWarning(0, None, "type_a", "msg"),
                ValidationWarning(1, None, "type_b", "msg"),
                ValidationWarning(2, None, "type_a", "msg"),
            ],
            feature_count=3,
            valid_feature_count=3,
        )
        type_a = result.get_warnings_by_type("type_a")
        assert len(type_a) == 2

    def test_to_summary(self) -> None:
        """Test summary generation."""
        result = ValidationResult(
            valid=True,
            warnings=[
                ValidationWarning(0, None, "out_of_bounds", "test"),
            ],
            feature_count=10,
            valid_feature_count=9,
        )
        summary = result.to_summary()
        assert "10 features" in summary
        assert "out_of_bounds" in summary


class TestGeometryValidator:
    """Test GeometryValidator class."""

    def test_validate_feature_collection(self) -> None:
        """Test validating a valid FeatureCollection."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        assert result.valid
        assert result.feature_count == 1
        assert result.valid_feature_count == 1

    def test_validate_out_of_bounds_longitude(self) -> None:
        """Test warning for out-of-bounds longitude."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [200, 0]},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        assert result.valid  # Warnings don't make it invalid
        warnings = result.get_warnings_by_type("out_of_bounds")
        assert len(warnings) > 0
        assert "Longitude" in warnings[0].message

    def test_validate_out_of_bounds_latitude(self) -> None:
        """Test warning for out-of-bounds latitude."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0, 100]},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        warnings = result.get_warnings_by_type("out_of_bounds")
        assert len(warnings) > 0
        assert "Latitude" in warnings[0].message

    def test_validate_null_geometry(self) -> None:
        """Test warning for null geometry."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        warnings = result.get_warnings_by_type("null_geometry")
        assert len(warnings) > 0

    def test_validate_invalid_feature_type(self) -> None:
        """Test error for invalid feature type."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "NotAFeature",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        assert not result.valid
        errors = [w for w in result.warnings if w.severity == "error"]
        assert len(errors) > 0

    def test_validate_linestring_too_few_points(self) -> None:
        """Test error for LineString with too few points."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[0, 0]]},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        assert not result.valid
        errors = result.get_warnings_by_type("insufficient_coordinates")
        assert len(errors) > 0

    def test_validate_polygon_too_few_points(self) -> None:
        """Test error for Polygon with too few points."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        errors = result.get_warnings_by_type("insufficient_coordinates")
        assert len(errors) > 0

    def test_validate_unclosed_polygon(self) -> None:
        """Test warning for unclosed polygon ring."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]],  # Not closed
                    },
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        warnings = result.get_warnings_by_type("unclosed_ring")
        assert len(warnings) > 0

    def test_validate_duplicate_vertices(self) -> None:
        """Test info for duplicate consecutive vertices."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 0], [0, 0], [1, 1], [1, 1], [2, 2]],
                    },
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        warnings = result.get_warnings_by_type("duplicate_vertices")
        assert len(warnings) > 0

    def test_validate_unknown_geometry_type(self) -> None:
        """Test error for unknown geometry type."""
        validator = GeometryValidator()
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "UnknownType", "coordinates": []},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        assert not result.valid
        errors = result.get_warnings_by_type("unknown_geometry_type")
        assert len(errors) > 0

    def test_validate_single_feature(self) -> None:
        """Test validating a single Feature (not collection)."""
        validator = GeometryValidator()
        geojson = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {},
        }

        result = validator.validate(geojson)
        assert result.valid
        assert result.feature_count == 1

    def test_validate_bare_geometry(self) -> None:
        """Test validating a bare geometry."""
        validator = GeometryValidator()
        geojson = {"type": "Point", "coordinates": [0, 0]}

        result = validator.validate(geojson)
        assert result.valid
        assert result.feature_count == 1

    def test_validate_max_warnings_limit(self) -> None:
        """Test max warnings limit."""
        validator = GeometryValidator(max_warnings=5)
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [200, 0]},  # Out of bounds
                    "properties": {},
                }
                for _ in range(100)
            ],
        }

        result = validator.validate(geojson)
        # Should have at most max_warnings + 1 (for the limit message)
        assert len(result.warnings) <= 6

    def test_disable_checks(self) -> None:
        """Test disabling specific checks."""
        validator = GeometryValidator(
            check_coordinates=False,
            check_winding=False,
            check_duplicates=False,
            check_closure=False,
        )
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [200, 100]},
                    "properties": {},
                }
            ],
        }

        result = validator.validate(geojson)
        # Should not have out_of_bounds warning
        assert len(result.get_warnings_by_type("out_of_bounds")) == 0


class TestValidateGeoJSONFunction:
    """Test the convenience function."""

    def test_validate_geojson_valid(self) -> None:
        """Test convenience function with valid data."""
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": {},
                }
            ],
        }

        result = validate_geojson(geojson)
        assert result.valid

    def test_validate_geojson_with_options(self) -> None:
        """Test convenience function with options."""
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [200, 0]},
                    "properties": {},
                }
            ],
        }

        result = validate_geojson(geojson, check_coordinates=False)
        # No out_of_bounds because we disabled coordinate checks
        assert len(result.get_warnings_by_type("out_of_bounds")) == 0
