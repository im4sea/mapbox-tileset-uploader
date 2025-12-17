"""
Core uploader module for Mapbox Tileset operations.
"""

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from mapbox_tileset_uploader.converters import get_converter, get_supported_formats
from mapbox_tileset_uploader.converters.base import ConversionResult
from mapbox_tileset_uploader.validators import GeometryValidator, ValidationResult


@dataclass
class TilesetConfig:
    """Configuration for a tileset upload."""

    tileset_id: str
    tileset_name: str
    source_id: str | None = None
    layer_name: str = "data"
    min_zoom: int = 0
    max_zoom: int = 10
    description: str = ""
    attribution: str = ""
    recipe: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set defaults after initialization."""
        if not self.source_id:
            self.source_id = self.tileset_id.replace(".", "-")


@dataclass
class UploadResult:
    """Result of a tileset upload operation."""

    success: bool
    tileset_id: str
    source_id: str | None
    steps: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    validation_result: ValidationResult | None = None
    conversion_result: ConversionResult | None = None
    job_id: str = ""
    job_status: str = ""
    error: str = ""
    dry_run: bool = False


class TilesetUploader:
    """
    Upload GeoJSON and other GIS formats to Mapbox as vector tilesets.

    This class wraps the mapbox-tilesets CLI to provide a Python interface
    for uploading geographic data to Mapbox Tiling Service (MTS).

    Supports multiple input formats through the modular converter system:
    - GeoJSON (.geojson, .json)
    - TopoJSON (.topojson)
    - Shapefile (.shp, .zip)
    - GeoPackage (.gpkg)
    - KML/KMZ (.kml, .kmz)
    - FlatGeobuf (.fgb)
    - GeoParquet (.parquet, .geoparquet)
    - GPX (.gpx)
    """

    def __init__(
        self,
        access_token: str | None = None,
        username: str | None = None,
        validate_geometry: bool = True,
    ) -> None:
        """
        Initialize the uploader.

        Args:
            access_token: Mapbox access token. If not provided, uses MAPBOX_ACCESS_TOKEN env var.
            username: Mapbox username. If not provided, uses MAPBOX_USERNAME env var.
            validate_geometry: Whether to validate geometries and warn about issues.
        """
        self.access_token = access_token or os.environ.get("MAPBOX_ACCESS_TOKEN")
        self.username = username or os.environ.get("MAPBOX_USERNAME")
        self.validate_geometry = validate_geometry

        if not self.access_token:
            raise ValueError(
                "Mapbox access token required. "
                "Set MAPBOX_ACCESS_TOKEN environment variable or pass access_token parameter."
            )
        if not self.username:
            raise ValueError(
                "Mapbox username required. "
                "Set MAPBOX_USERNAME environment variable or pass username parameter."
            )

        # Set environment variable for tilesets CLI
        os.environ["MAPBOX_ACCESS_TOKEN"] = self.access_token

        # Initialize validator
        self._validator = GeometryValidator() if validate_geometry else None

    def upload_from_url(
        self,
        url: str,
        config: TilesetConfig,
        format_hint: str | None = None,
        work_dir: str | None = None,
        dry_run: bool = False,
    ) -> UploadResult:
        """
        Download data from URL and upload to Mapbox.

        Args:
            url: URL to download GeoJSON or other GIS format from.
            config: Tileset configuration.
            format_hint: Explicit format name (auto-detected if not provided).
            work_dir: Working directory for temporary files.
            dry_run: If True, validate but don't upload.

        Returns:
            UploadResult with upload details.
        """
        work_path = Path(work_dir) if work_dir else Path(tempfile.mkdtemp())
        work_path.mkdir(parents=True, exist_ok=True)

        # Determine file type from URL
        url_lower = url.lower()
        ext = ".geojson"
        for fmt_ext in [".topojson", ".shp", ".gpkg", ".kml", ".kmz", ".fgb", ".parquet", ".gpx"]:
            if fmt_ext in url_lower:
                ext = fmt_ext
                break

        download_path = work_path / f"source{ext}"

        try:
            # Download the file
            self._download_file(url, download_path)

            # Upload from the downloaded file
            return self.upload_from_file(
                download_path,
                config,
                format_hint=format_hint,
                dry_run=dry_run,
            )

        finally:
            # Clean up if using temp directory
            if not work_dir:
                import shutil

                shutil.rmtree(work_path, ignore_errors=True)

    def upload_from_file(
        self,
        file_path: str | Path,
        config: TilesetConfig,
        format_hint: str | None = None,
        dry_run: bool = False,
    ) -> UploadResult:
        """
        Upload a GIS file to Mapbox.

        Args:
            file_path: Path to the file to upload.
            config: Tileset configuration.
            format_hint: Explicit format name (auto-detected if not provided).
            dry_run: If True, validate but don't upload.

        Returns:
            UploadResult with upload details.
        """
        file_path = Path(file_path)
        result = UploadResult(
            success=False,
            tileset_id=f"{self.username}.{config.tileset_id}",
            source_id=config.source_id,
            dry_run=dry_run,
        )

        try:
            # Get converter for the file format
            converter = get_converter(format_name=format_hint, file_path=file_path)

            # Convert to GeoJSON
            conversion = converter.convert(file_path)
            result.conversion_result = conversion
            result.warnings.extend(conversion.warnings)
            result.steps["convert"] = True

            geojson = conversion.geojson

            # Validate geometry
            if self._validator:
                validation = self._validator.validate(geojson)
                result.validation_result = validation
                result.steps["validate"] = True

                # Add validation warnings to result
                for warning in validation.warnings:
                    if warning.severity in ("warning", "error"):
                        result.warnings.append(f"[{warning.warning_type}] {warning.message}")

            if dry_run:
                result.success = True
                return result

            # Write GeoJSON to temp file for upload
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".geojson",
                delete=False,
                encoding="utf-8",
            ) as f:
                json.dump(geojson, f)
                geojson_path = Path(f.name)

            try:
                # Upload source
                self._upload_source(geojson_path, config.source_id)
                result.steps["upload_source"] = True

                # Create or update tileset
                full_tileset_id = f"{self.username}.{config.tileset_id}"
                recipe = self._build_recipe(config)

                if self._tileset_exists(full_tileset_id):
                    self._update_recipe(full_tileset_id, recipe)
                    result.steps["update_recipe"] = True
                else:
                    self._create_tileset(full_tileset_id, recipe, config)
                    result.steps["create_tileset"] = True

                # Publish tileset
                job_id = self._publish_tileset(full_tileset_id)
                result.steps["publish"] = True
                result.job_id = job_id

                # Wait for completion
                status = self._wait_for_job(full_tileset_id, job_id)
                result.steps["job_complete"] = True
                result.job_status = status

                result.success = status == "success"

            finally:
                geojson_path.unlink(missing_ok=True)

        except Exception as e:
            result.error = str(e)

        return result

    def _download_file(self, url: str, dest_path: Path) -> None:
        """Download a file from URL."""
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def _run_tilesets_command(
        self,
        args: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a tilesets CLI command."""
        cmd = ["tilesets"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"Tilesets command failed: {result.stderr}")
        return result

    def _upload_source(self, file_path: Path, source_id: str | None) -> None:
        """Upload file to tileset source."""
        if source_id is None:
            raise ValueError("source_id is required for uploading")
        self._run_tilesets_command(
            ["upload-source", "--replace", self.username, source_id, str(file_path)]
        )

    def _tileset_exists(self, tileset_id: str) -> bool:
        """Check if tileset already exists."""
        result = self._run_tilesets_command(["status", tileset_id], check=False)
        return result.returncode == 0

    def _build_recipe(self, config: TilesetConfig) -> dict[str, Any]:
        """Build tileset recipe."""
        if config.recipe:
            return config.recipe

        return {
            "version": 1,
            "layers": {
                config.layer_name: {
                    "source": f"mapbox://tileset-source/{self.username}/{config.source_id}",
                    "minzoom": config.min_zoom,
                    "maxzoom": config.max_zoom,
                }
            },
        }

    def _create_tileset(
        self,
        tileset_id: str,
        recipe: dict[str, Any],
        config: TilesetConfig,
    ) -> None:
        """Create a new tileset."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(recipe, f)
            recipe_path = f.name

        try:
            args = [
                "create",
                tileset_id,
                "--recipe",
                recipe_path,
                "--name",
                config.tileset_name,
            ]
            if config.description:
                args.extend(["--description", config.description])
            if config.attribution:
                args.extend(["--attribution", config.attribution])

            self._run_tilesets_command(args)
        finally:
            os.unlink(recipe_path)

    def _update_recipe(self, tileset_id: str, recipe: dict[str, Any]) -> None:
        """Update tileset recipe."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(recipe, f)
            recipe_path = f.name

        try:
            self._run_tilesets_command(["update-recipe", tileset_id, recipe_path])
        finally:
            os.unlink(recipe_path)

    def _publish_tileset(self, tileset_id: str) -> str:
        """Publish tileset and return job ID."""
        result = self._run_tilesets_command(["publish", tileset_id])
        try:
            output = json.loads(result.stdout)
            return output.get("jobId", "")
        except json.JSONDecodeError:
            return ""

    def _wait_for_job(
        self,
        tileset_id: str,
        job_id: str,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> str:
        """Wait for tileset job to complete."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = self._run_tilesets_command(["status", tileset_id], check=False)

            if result.returncode == 0:
                try:
                    status_data = json.loads(result.stdout)
                    status = status_data.get("status", "unknown")

                    if status == "success":
                        return "success"
                    elif status in ("failed", "errored"):
                        return f"failed: {status_data.get('message', 'Unknown error')}"
                except json.JSONDecodeError:
                    pass

            time.sleep(poll_interval)

        return "timeout"

    def list_sources(self) -> list[dict[str, Any]]:
        """List all tileset sources for the user."""
        result = self._run_tilesets_command(["list-sources", self.username])
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

    def list_tilesets(self) -> list[dict[str, Any]]:
        """List all tilesets for the user."""
        result = self._run_tilesets_command(["list", self.username])
        try:
            lines = result.stdout.strip().split("\n")
            return [json.loads(line) for line in lines if line]
        except json.JSONDecodeError:
            return []

    def delete_source(self, source_id: str) -> bool:
        """Delete a tileset source."""
        result = self._run_tilesets_command(
            ["delete-source", "--force", self.username, source_id], check=False
        )
        return result.returncode == 0

    def delete_tileset(self, tileset_id: str) -> bool:
        """Delete a tileset."""
        full_id = f"{self.username}.{tileset_id}"
        result = self._run_tilesets_command(["delete", "--force", full_id], check=False)
        return result.returncode == 0

    @staticmethod
    def get_supported_formats() -> list[dict[str, Any]]:
        """Get list of supported input formats."""
        return get_supported_formats()
