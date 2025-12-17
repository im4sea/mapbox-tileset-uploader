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
from typing import Any, Dict, List, Optional

import requests

from mapbox_tileset_uploader.converter import convert_topojson_to_geojson


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
    recipe: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set defaults after initialization."""
        if not self.source_id:
            self.source_id = self.tileset_id.replace(".", "-")


class TilesetUploader:
    """
    Upload GeoJSON and TopoJSON files to Mapbox as vector tilesets.

    This class wraps the mapbox-tilesets CLI to provide a Python interface
    for uploading geographic data to Mapbox Tiling Service (MTS).
    """

    def __init__(
        self,
        access_token: str | None = None,
        username: str | None = None,
    ) -> None:
        """
        Initialize the uploader.

        Args:
            access_token: Mapbox access token. If not provided, uses MAPBOX_ACCESS_TOKEN env var.
            username: Mapbox username. If not provided, uses MAPBOX_USERNAME env var.
        """
        self.access_token = access_token or os.environ.get("MAPBOX_ACCESS_TOKEN")
        self.username = username or os.environ.get("MAPBOX_USERNAME")

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

    def upload_from_url(
        self,
        url: str,
        config: TilesetConfig,
        work_dir: str | None = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Download data from URL and upload to Mapbox.

        Args:
            url: URL to download GeoJSON or TopoJSON from
            config: Tileset configuration
            work_dir: Working directory for temporary files
            dry_run: If True, validate but don't upload

        Returns:
            Dictionary with upload results
        """
        work_path = Path(work_dir) if work_dir else Path(tempfile.mkdtemp())
        work_path.mkdir(parents=True, exist_ok=True)

        # Determine file type from URL
        is_topojson = ".topojson" in url.lower() or "topojson" in url.lower()
        ext = ".topojson" if is_topojson else ".geojson"
        download_path = work_path / f"source{ext}"
        geojson_path = work_path / "source.geojson"

        try:
            # Download the file
            self._download_file(url, download_path)

            # Convert TopoJSON to GeoJSON if needed
            if is_topojson:
                geojson = self._convert_topojson(download_path)
                with open(geojson_path, "w", encoding="utf-8") as f:
                    json.dump(geojson, f)
            else:
                geojson_path = download_path

            # Upload to Mapbox
            return self.upload_from_file(geojson_path, config, dry_run=dry_run)

        finally:
            # Clean up if using temp directory
            if not work_dir:
                import shutil

                shutil.rmtree(work_path, ignore_errors=True)

    def upload_from_file(
        self,
        file_path: str | Path,
        config: TilesetConfig,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Upload a GeoJSON or TopoJSON file to Mapbox.

        Args:
            file_path: Path to the file to upload
            config: Tileset configuration
            dry_run: If True, validate but don't upload

        Returns:
            Dictionary with upload results
        """
        file_path = Path(file_path)
        results: Dict[str, Any] = {
            "success": False,
            "tileset_id": f"{self.username}.{config.tileset_id}",
            "source_id": config.source_id,
            "steps": {},
        }

        try:
            # Convert TopoJSON if needed
            if file_path.suffix.lower() == ".topojson":
                geojson = self._convert_topojson(file_path)
                temp_path = file_path.parent / f"{file_path.stem}.geojson"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(geojson, f)
                file_path = temp_path

            # Validate GeoJSON
            self._validate_geojson(file_path)
            results["steps"]["validate"] = True

            if dry_run:
                results["success"] = True
                results["dry_run"] = True
                return results

            # Upload source
            self._upload_source(file_path, config.source_id)
            results["steps"]["upload_source"] = True

            # Create or update tileset
            full_tileset_id = f"{self.username}.{config.tileset_id}"
            recipe = self._build_recipe(config)

            if self._tileset_exists(full_tileset_id):
                self._update_recipe(full_tileset_id, recipe)
                results["steps"]["update_recipe"] = True
            else:
                self._create_tileset(full_tileset_id, recipe, config)
                results["steps"]["create_tileset"] = True

            # Publish tileset
            job_id = self._publish_tileset(full_tileset_id)
            results["steps"]["publish"] = True
            results["job_id"] = job_id

            # Wait for completion
            status = self._wait_for_job(full_tileset_id, job_id)
            results["steps"]["job_complete"] = True
            results["job_status"] = status

            results["success"] = status == "success"

        except Exception as e:
            results["error"] = str(e)

        return results

    def _download_file(self, url: str, dest_path: Path) -> None:
        """Download a file from URL."""
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def _convert_topojson(self, file_path: Path) -> Dict[str, Any]:
        """Convert TopoJSON file to GeoJSON."""
        with open(file_path, "r", encoding="utf-8") as f:
            topojson = json.load(f)
        return convert_topojson_to_geojson(topojson)

    def _validate_geojson(self, file_path: Path) -> None:
        """Validate GeoJSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("type") not in ("FeatureCollection", "Feature", "GeometryCollection"):
            valid_types = ", ".join(data.get("features", [{}])[0].get("geometry", {}).keys())
            if data.get("type") not in (
                "Point",
                "MultiPoint",
                "LineString",
                "MultiLineString",
                "Polygon",
                "MultiPolygon",
            ):
                raise ValueError(f"Invalid GeoJSON type: {data.get('type')}")

    def _run_tilesets_command(
        self,
        args: List[str],
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
        full_source_id = f"{self.username}.{source_id}"
        self._run_tilesets_command(
            ["upload-source", "--replace", self.username, source_id, str(file_path)]
        )

    def _tileset_exists(self, tileset_id: str) -> bool:
        """Check if tileset already exists."""
        result = self._run_tilesets_command(["status", tileset_id], check=False)
        return result.returncode == 0

    def _build_recipe(self, config: TilesetConfig) -> Dict[str, Any]:
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
        recipe: Dict[str, Any],
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

    def _update_recipe(self, tileset_id: str, recipe: Dict[str, Any]) -> None:
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
        # Parse job ID from output
        try:
            output = json.loads(result.stdout)
            return output.get("jobId", "")
        except json.JSONDecodeError:
            # Try to extract from text output
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

    def list_sources(self) -> List[Dict[str, Any]]:
        """List all tileset sources for the user."""
        result = self._run_tilesets_command(["list-sources", self.username])
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

    def list_tilesets(self) -> List[Dict[str, Any]]:
        """List all tilesets for the user."""
        result = self._run_tilesets_command(["list", self.username])
        try:
            lines = result.stdout.strip().split("\n")
            return [json.loads(line) for line in lines if line]
        except json.JSONDecodeError:
            return []

    def delete_source(self, source_id: str) -> bool:
        """Delete a tileset source."""
        full_id = f"{self.username}.{source_id}"
        result = self._run_tilesets_command(
            ["delete-source", "--force", self.username, source_id], check=False
        )
        return result.returncode == 0

    def delete_tileset(self, tileset_id: str) -> bool:
        """Delete a tileset."""
        full_id = f"{self.username}.{tileset_id}"
        result = self._run_tilesets_command(["delete", "--force", full_id], check=False)
        return result.returncode == 0
