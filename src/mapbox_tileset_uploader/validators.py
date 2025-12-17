"""
Geometry validation module.

Provides warnings for geometry issues without modifying the data.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ValidationWarning:
    """A single validation warning."""

    feature_index: Optional[int]
    """Index of the feature with the issue, or None for global issues."""

    feature_id: Optional[Any]
    """ID of the feature, if available."""

    warning_type: str
    """Category of warning (e.g., 'invalid_geometry', 'missing_crs')."""

    message: str
    """Human-readable warning message."""

    severity: str = "warning"
    """Severity level: 'info', 'warning', 'error'."""

    details: dict[str, Any] = field(default_factory=dict)
    """Additional details about the issue."""


@dataclass
class ValidationResult:
    """Result of geometry validation."""

    valid: bool
    """Whether the data passed validation (no errors, warnings OK)."""

    warnings: list[ValidationWarning] = field(default_factory=list)
    """List of validation warnings."""

    feature_count: int = 0
    """Total number of features validated."""

    valid_feature_count: int = 0
    """Number of features that passed validation."""

    @property
    def warning_count(self) -> int:
        """Number of warnings."""
        return len([w for w in self.warnings if w.severity == "warning"])

    @property
    def error_count(self) -> int:
        """Number of errors."""
        return len([w for w in self.warnings if w.severity == "error"])

    def get_warnings_by_type(self, warning_type: str) -> list[ValidationWarning]:
        """Get all warnings of a specific type."""
        return [w for w in self.warnings if w.warning_type == warning_type]

    def to_summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"Validated {self.feature_count} features",
            f"  Valid: {self.valid_feature_count}",
            f"  Warnings: {self.warning_count}",
            f"  Errors: {self.error_count}",
        ]

        if self.warnings:
            lines.append("\nIssues found:")
            # Group by type
            types: dict[str, int] = {}
            for w in self.warnings:
                types[w.warning_type] = types.get(w.warning_type, 0) + 1

            for wtype, count in sorted(types.items()):
                lines.append(f"  - {wtype}: {count}")

        return "\n".join(lines)


class GeometryValidator:
    """
    Validates GeoJSON geometries and provides warnings.

    This validator checks for common geometry issues but does NOT
    modify the data. It only reports problems so users can be informed.
    """

    # Valid coordinate ranges
    LON_MIN = -180.0
    LON_MAX = 180.0
    LAT_MIN = -90.0
    LAT_MAX = 90.0

    def __init__(
        self,
        check_coordinates: bool = True,
        check_winding: bool = True,
        check_duplicates: bool = True,
        check_closure: bool = True,
        check_validity: bool = True,
        max_warnings: int = 100,
    ) -> None:
        """
        Initialize the validator.

        Args:
            check_coordinates: Check for out-of-bounds coordinates.
            check_winding: Check polygon winding order (RFC 7946).
            check_duplicates: Check for duplicate consecutive vertices.
            check_closure: Check that polygon rings are closed.
            check_validity: Check for self-intersection (requires shapely).
            max_warnings: Maximum warnings to collect (prevents memory issues).
        """
        self.check_coordinates = check_coordinates
        self.check_winding = check_winding
        self.check_duplicates = check_duplicates
        self.check_closure = check_closure
        self.check_validity = check_validity
        self.max_warnings = max_warnings

        # Check if shapely is available for validity checks
        self._has_shapely = False
        if check_validity:
            try:
                import shapely  # noqa: F401

                self._has_shapely = True
            except ImportError:
                pass

    def validate(self, geojson: dict[str, Any]) -> ValidationResult:
        """
        Validate a GeoJSON object.

        Args:
            geojson: GeoJSON data to validate.

        Returns:
            ValidationResult with warnings and statistics.
        """
        warnings: list[ValidationWarning] = []
        valid_count = 0
        total_count = 0

        geojson_type = geojson.get("type")

        if geojson_type == "FeatureCollection":
            features = geojson.get("features", [])
            for i, feature in enumerate(features):
                if len(warnings) >= self.max_warnings:
                    msg = f"Maximum warnings ({self.max_warnings}) reached"
                    warnings.append(
                        ValidationWarning(
                            feature_index=None,
                            feature_id=None,
                            warning_type="max_warnings_reached",
                            message=msg + ", stopping validation",
                            severity="info",
                        )
                    )
                    break

                total_count += 1
                feature_warnings = self._validate_feature(feature, i)
                warnings.extend(feature_warnings)

                if not any(w.severity == "error" for w in feature_warnings):
                    valid_count += 1

        elif geojson_type == "Feature":
            total_count = 1
            feature_warnings = self._validate_feature(geojson, 0)
            warnings.extend(feature_warnings)
            if not any(w.severity == "error" for w in feature_warnings):
                valid_count = 1

        elif geojson_type in (
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
            "GeometryCollection",
        ):
            total_count = 1
            geom_warnings = self._validate_geometry(geojson, 0, None)
            warnings.extend(geom_warnings)
            if not any(w.severity == "error" for w in geom_warnings):
                valid_count = 1

        else:
            warnings.append(
                ValidationWarning(
                    feature_index=None,
                    feature_id=None,
                    warning_type="invalid_type",
                    message=f"Invalid GeoJSON type: {geojson_type}",
                    severity="error",
                )
            )

        return ValidationResult(
            valid=len([w for w in warnings if w.severity == "error"]) == 0,
            warnings=warnings,
            feature_count=total_count,
            valid_feature_count=valid_count,
        )

    def _validate_feature(
        self,
        feature: dict[str, Any],
        index: int,
    ) -> list[ValidationWarning]:
        """Validate a single feature."""
        warnings: list[ValidationWarning] = []
        feature_id = feature.get("id")

        # Check feature structure
        if feature.get("type") != "Feature":
            warnings.append(
                ValidationWarning(
                    feature_index=index,
                    feature_id=feature_id,
                    warning_type="invalid_feature",
                    message=f"Invalid feature type: {feature.get('type')}",
                    severity="error",
                )
            )
            return warnings

        # Check geometry
        geometry = feature.get("geometry")
        if geometry is None:
            warnings.append(
                ValidationWarning(
                    feature_index=index,
                    feature_id=feature_id,
                    warning_type="null_geometry",
                    message="Feature has null geometry",
                    severity="warning",
                )
            )
        else:
            warnings.extend(self._validate_geometry(geometry, index, feature_id))

        # Check properties
        props = feature.get("properties")
        if props is None:
            warnings.append(
                ValidationWarning(
                    feature_index=index,
                    feature_id=feature_id,
                    warning_type="null_properties",
                    message="Feature has null properties (should be empty object {})",
                    severity="info",
                )
            )

        return warnings

    def _validate_geometry(
        self,
        geometry: dict[str, Any],
        feature_index: int,
        feature_id: Optional[Any],
    ) -> list[ValidationWarning]:
        """Validate a geometry."""
        warnings: list[ValidationWarning] = []
        geom_type = geometry.get("type")

        if geom_type == "Point":
            coords = geometry.get("coordinates", [])
            warnings.extend(self._validate_coordinate(coords, feature_index, feature_id))

        elif geom_type == "MultiPoint":
            for coord in geometry.get("coordinates", []):
                warnings.extend(self._validate_coordinate(coord, feature_index, feature_id))

        elif geom_type == "LineString":
            coords = geometry.get("coordinates", [])
            warnings.extend(self._validate_line_string(coords, feature_index, feature_id))

        elif geom_type == "MultiLineString":
            for line in geometry.get("coordinates", []):
                warnings.extend(self._validate_line_string(line, feature_index, feature_id))

        elif geom_type == "Polygon":
            rings = geometry.get("coordinates", [])
            warnings.extend(self._validate_polygon(rings, feature_index, feature_id))

        elif geom_type == "MultiPolygon":
            for polygon in geometry.get("coordinates", []):
                warnings.extend(self._validate_polygon(polygon, feature_index, feature_id))

        elif geom_type == "GeometryCollection":
            for geom in geometry.get("geometries", []):
                warnings.extend(self._validate_geometry(geom, feature_index, feature_id))

        elif geom_type is None:
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="null_geometry",
                    message="Geometry type is null",
                    severity="warning",
                )
            )

        else:
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="unknown_geometry_type",
                    message=f"Unknown geometry type: {geom_type}",
                    severity="error",
                )
            )

        # Check validity using shapely if available
        if self.check_validity and self._has_shapely:
            validity_warnings = self._check_shapely_validity(geometry, feature_index, feature_id)
            warnings.extend(validity_warnings)

        return warnings

    def _validate_coordinate(
        self,
        coord: list[float],
        feature_index: int,
        feature_id: Optional[Any],
    ) -> list[ValidationWarning]:
        """Validate a single coordinate."""
        warnings: list[ValidationWarning] = []

        if not self.check_coordinates:
            return warnings

        if not coord or len(coord) < 2:
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="invalid_coordinate",
                    message=f"Invalid coordinate: {coord}",
                    severity="error",
                )
            )
            return warnings

        lon, lat = coord[0], coord[1]

        if not (self.LON_MIN <= lon <= self.LON_MAX):
            msg = f"Longitude {lon} is out of range [{self.LON_MIN}, {self.LON_MAX}]"
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="out_of_bounds",
                    message=msg,
                    severity="warning",
                    details={"coordinate": coord},
                )
            )

        if not (self.LAT_MIN <= lat <= self.LAT_MAX):
            msg = f"Latitude {lat} is out of range [{self.LAT_MIN}, {self.LAT_MAX}]"
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="out_of_bounds",
                    message=msg,
                    severity="warning",
                    details={"coordinate": coord},
                )
            )

        return warnings

    def _validate_line_string(
        self,
        coords: list[list[float]],
        feature_index: int,
        feature_id: Optional[Any],
    ) -> list[ValidationWarning]:
        """Validate a LineString."""
        warnings: list[ValidationWarning] = []

        if len(coords) < 2:
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="insufficient_coordinates",
                    message=f"LineString has {len(coords)} points, needs at least 2",
                    severity="error",
                )
            )
            return warnings

        # Check individual coordinates
        for coord in coords:
            warnings.extend(self._validate_coordinate(coord, feature_index, feature_id))

        # Check for duplicate consecutive vertices
        if self.check_duplicates:
            duplicates = self._find_consecutive_duplicates(coords)
            if duplicates:
                warnings.append(
                    ValidationWarning(
                        feature_index=feature_index,
                        feature_id=feature_id,
                        warning_type="duplicate_vertices",
                        message=f"LineString has {len(duplicates)} duplicate consecutive vertices",
                        severity="info",
                        details={"duplicate_indices": duplicates[:5]},  # Limit details
                    )
                )

        return warnings

    def _validate_polygon(
        self,
        rings: list[list[list[float]]],
        feature_index: int,
        feature_id: Optional[Any],
    ) -> list[ValidationWarning]:
        """Validate a Polygon."""
        warnings: list[ValidationWarning] = []

        if not rings:
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="empty_polygon",
                    message="Polygon has no rings",
                    severity="error",
                )
            )
            return warnings

        for ring_index, ring in enumerate(rings):
            ring_type = "exterior" if ring_index == 0 else f"hole {ring_index}"

            # Check minimum points
            if len(ring) < 4:
                msg = f"Polygon {ring_type} ring has {len(ring)} points, needs 4"
                warnings.append(
                    ValidationWarning(
                        feature_index=feature_index,
                        feature_id=feature_id,
                        warning_type="insufficient_coordinates",
                        message=msg,
                        severity="error",
                    )
                )
                continue

            # Check closure
            if self.check_closure:
                if ring[0] != ring[-1]:
                    warnings.append(
                        ValidationWarning(
                            feature_index=feature_index,
                            feature_id=feature_id,
                            warning_type="unclosed_ring",
                            message=f"Polygon {ring_type} ring is not closed",
                            severity="warning",
                            details={
                                "first": ring[0],
                                "last": ring[-1],
                            },
                        )
                    )

            # Check coordinates
            for coord in ring:
                warnings.extend(self._validate_coordinate(coord, feature_index, feature_id))

            # Check duplicates
            if self.check_duplicates:
                duplicates = self._find_consecutive_duplicates(ring)
                # Exclude the closing point duplicate
                if ring[0] == ring[-1] and len(ring) - 1 in duplicates:
                    duplicates.remove(len(ring) - 1)
                if duplicates:
                    dupe_count = len(duplicates)
                    msg = f"Polygon {ring_type} ring has {dupe_count} duplicate vertices"
                    warnings.append(
                        ValidationWarning(
                            feature_index=feature_index,
                            feature_id=feature_id,
                            warning_type="duplicate_vertices",
                            message=msg,
                            severity="info",
                        )
                    )

            # Check winding order (RFC 7946)
            if self.check_winding and len(ring) >= 4:
                is_ccw = self._is_counterclockwise(ring)
                if ring_index == 0 and is_ccw:
                    warnings.append(
                        ValidationWarning(
                            feature_index=feature_index,
                            feature_id=feature_id,
                            warning_type="wrong_winding",
                            message="Exterior ring should be clockwise (RFC 7946)",
                            severity="info",
                        )
                    )
                elif ring_index > 0 and not is_ccw:
                    warnings.append(
                        ValidationWarning(
                            feature_index=feature_index,
                            feature_id=feature_id,
                            warning_type="wrong_winding",
                            message=f"Hole {ring_index} should be counter-clockwise (RFC 7946)",
                            severity="info",
                        )
                    )

        return warnings

    def _find_consecutive_duplicates(
        self,
        coords: list[list[float]],
    ) -> list[int]:
        """Find indices of consecutive duplicate vertices."""
        duplicates = []
        for i in range(1, len(coords)):
            if coords[i] == coords[i - 1]:
                duplicates.append(i)
        return duplicates

    def _is_counterclockwise(self, ring: list[list[float]]) -> bool:
        """Check if a ring is counter-clockwise using the shoelace formula."""
        total = 0.0
        n = len(ring)
        for i in range(n - 1):
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[i + 1][0], ring[i + 1][1]
            total += (x2 - x1) * (y2 + y1)
        return total < 0

    def _check_shapely_validity(
        self,
        geometry: dict[str, Any],
        feature_index: int,
        feature_id: Optional[Any],
    ) -> list[ValidationWarning]:
        """Check geometry validity using shapely."""
        warnings: list[ValidationWarning] = []

        try:
            from shapely.geometry import shape
            from shapely.validation import explain_validity

            geom = shape(geometry)

            if not geom.is_valid:
                reason = explain_validity(geom)
                warnings.append(
                    ValidationWarning(
                        feature_index=feature_index,
                        feature_id=feature_id,
                        warning_type="invalid_geometry",
                        message=f"Invalid geometry: {reason}",
                        severity="warning",
                        details={"shapely_reason": reason},
                    )
                )

            if geom.is_empty:
                warnings.append(
                    ValidationWarning(
                        feature_index=feature_index,
                        feature_id=feature_id,
                        warning_type="empty_geometry",
                        message="Geometry is empty",
                        severity="warning",
                    )
                )

        except Exception as e:
            warnings.append(
                ValidationWarning(
                    feature_index=feature_index,
                    feature_id=feature_id,
                    warning_type="validation_error",
                    message=f"Could not validate geometry: {e}",
                    severity="info",
                )
            )

        return warnings


def validate_geojson(
    geojson: dict[str, Any],
    **options: Any,
) -> ValidationResult:
    """
    Convenience function to validate GeoJSON.

    Args:
        geojson: GeoJSON data to validate.
        **options: Options passed to GeometryValidator.

    Returns:
        ValidationResult with warnings and statistics.
    """
    validator = GeometryValidator(**options)
    return validator.validate(geojson)
