"""
Command-line interface for Mapbox Tileset Uploader.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from mapbox_tileset_uploader import __version__
from mapbox_tileset_uploader.converter import convert_topojson_to_geojson, load_and_convert
from mapbox_tileset_uploader.uploader import TilesetConfig, TilesetUploader


@click.group()
@click.version_option(version=__version__, prog_name="mapbox-tileset-uploader")
def main() -> None:
    """
    Mapbox Tileset Uploader - Upload GeoJSON and TopoJSON to Mapbox.

    A CLI tool to upload geographic data files to Mapbox as vector tilesets.
    Supports both local files and remote URLs, as well as GeoJSON and TopoJSON formats.

    \b
    Required environment variables:
      MAPBOX_ACCESS_TOKEN  Your Mapbox access token with tilesets:write scope
      MAPBOX_USERNAME      Your Mapbox username

    \b
    Examples:
      # Upload from URL
      mtu upload --url https://example.com/data.geojson --id my-tileset --name "My Tileset"

      # Upload from local file
      mtu upload --file data.geojson --id my-tileset --name "My Tileset"

      # Convert TopoJSON to GeoJSON
      mtu convert input.topojson output.geojson
    """
    pass


@main.command()
@click.option("--url", "-u", help="URL to download GeoJSON/TopoJSON from")
@click.option("--file", "-f", "file_path", type=click.Path(exists=True), help="Local file path")
@click.option("--id", "-i", "tileset_id", required=True, help="Tileset ID (without username prefix)")
@click.option("--name", "-n", "tileset_name", required=True, help="Human-readable tileset name")
@click.option("--source-id", "-s", help="Source ID (defaults to tileset ID with dots replaced)")
@click.option("--layer", "-l", "layer_name", default="data", help="Layer name in the tileset")
@click.option("--min-zoom", default=0, type=int, help="Minimum zoom level (0-22)")
@click.option("--max-zoom", default=10, type=int, help="Maximum zoom level (0-22)")
@click.option("--description", "-d", default="", help="Tileset description")
@click.option("--attribution", "-a", default="", help="Tileset attribution")
@click.option("--recipe", "-r", type=click.Path(exists=True), help="Custom recipe JSON file")
@click.option("--work-dir", "-w", type=click.Path(), help="Working directory for temp files")
@click.option("--dry-run", is_flag=True, help="Validate without uploading")
@click.option("--token", envvar="MAPBOX_ACCESS_TOKEN", help="Mapbox access token")
@click.option("--username", envvar="MAPBOX_USERNAME", help="Mapbox username")
def upload(
    url: Optional[str],
    file_path: Optional[str],
    tileset_id: str,
    tileset_name: str,
    source_id: Optional[str],
    layer_name: str,
    min_zoom: int,
    max_zoom: int,
    description: str,
    attribution: str,
    recipe: Optional[str],
    work_dir: Optional[str],
    dry_run: bool,
    token: Optional[str],
    username: Optional[str],
) -> None:
    """
    Upload GeoJSON or TopoJSON to Mapbox as a vector tileset.

    Provide either --url to download from a remote source, or --file for a local file.

    \b
    Examples:
      # From URL
      mtu upload -u https://example.com/data.geojson -i my-tileset -n "My Tileset"

      # From file with custom zoom levels
      mtu upload -f data.geojson -i my-tileset -n "My Tileset" --min-zoom 2 --max-zoom 14

      # Dry run to validate
      mtu upload -f data.geojson -i my-tileset -n "My Tileset" --dry-run
    """
    if not url and not file_path:
        raise click.UsageError("Either --url or --file must be provided")

    if url and file_path:
        raise click.UsageError("Cannot specify both --url and --file")

    # Load custom recipe if provided
    custom_recipe = {}
    if recipe:
        with open(recipe, "r", encoding="utf-8") as f:
            custom_recipe = json.load(f)

    # Build configuration
    config = TilesetConfig(
        tileset_id=tileset_id,
        tileset_name=tileset_name,
        source_id=source_id,
        layer_name=layer_name,
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        description=description,
        attribution=attribution,
        recipe=custom_recipe,
    )

    try:
        uploader = TilesetUploader(access_token=token, username=username)
    except ValueError as e:
        raise click.ClickException(str(e))

    click.echo(f"📦 Uploading tileset: {username}.{tileset_id}")
    click.echo(f"   Name: {tileset_name}")
    click.echo(f"   Zoom: {min_zoom}-{max_zoom}")

    if dry_run:
        click.echo("   Mode: DRY RUN (validation only)")

    try:
        if url:
            click.echo(f"   Source: {url}")
            results = uploader.upload_from_url(url, config, work_dir=work_dir, dry_run=dry_run)
        else:
            click.echo(f"   Source: {file_path}")
            results = uploader.upload_from_file(file_path, config, dry_run=dry_run)  # type: ignore

        if results["success"]:
            click.echo("✅ Upload successful!")
            click.echo(f"   Tileset ID: {results['tileset_id']}")
            if not dry_run:
                click.echo(f"   View at: https://studio.mapbox.com/tilesets/{results['tileset_id']}/")
        else:
            click.echo("❌ Upload failed!")
            if "error" in results:
                click.echo(f"   Error: {results['error']}")
            sys.exit(1)

    except Exception as e:
        raise click.ClickException(str(e))


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.argument("output_file", type=click.Path())
@click.option("--object", "-o", "object_name", help="TopoJSON object name to convert")
@click.option("--pretty", "-p", is_flag=True, help="Pretty-print output JSON")
def convert(
    input_file: str,
    output_file: str,
    object_name: Optional[str],
    pretty: bool,
) -> None:
    """
    Convert TopoJSON to GeoJSON.

    \b
    Examples:
      mtu convert input.topojson output.geojson
      mtu convert input.topojson output.geojson --object countries --pretty
    """
    click.echo(f"🔄 Converting {input_file} to GeoJSON...")

    try:
        geojson = load_and_convert(input_file, object_name)

        with open(output_file, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(geojson, f, indent=2, ensure_ascii=False)
            else:
                json.dump(geojson, f, ensure_ascii=False)

        feature_count = len(geojson.get("features", []))
        click.echo(f"✅ Converted {feature_count} features to {output_file}")

    except Exception as e:
        raise click.ClickException(str(e))


@main.command("list-sources")
@click.option("--token", envvar="MAPBOX_ACCESS_TOKEN", help="Mapbox access token")
@click.option("--username", envvar="MAPBOX_USERNAME", help="Mapbox username")
def list_sources(token: Optional[str], username: Optional[str]) -> None:
    """List all tileset sources for your account."""
    try:
        uploader = TilesetUploader(access_token=token, username=username)
        sources = uploader.list_sources()

        if not sources:
            click.echo("No tileset sources found.")
            return

        click.echo(f"📂 Found {len(sources)} tileset source(s):")
        for source in sources:
            if isinstance(source, dict):
                click.echo(f"   - {source.get('id', source)}")
            else:
                click.echo(f"   - {source}")

    except Exception as e:
        raise click.ClickException(str(e))


@main.command("list-tilesets")
@click.option("--token", envvar="MAPBOX_ACCESS_TOKEN", help="Mapbox access token")
@click.option("--username", envvar="MAPBOX_USERNAME", help="Mapbox username")
def list_tilesets(token: Optional[str], username: Optional[str]) -> None:
    """List all tilesets for your account."""
    try:
        uploader = TilesetUploader(access_token=token, username=username)
        tilesets = uploader.list_tilesets()

        if not tilesets:
            click.echo("No tilesets found.")
            return

        click.echo(f"🗺️  Found {len(tilesets)} tileset(s):")
        for tileset in tilesets:
            if isinstance(tileset, dict):
                name = tileset.get("name", tileset.get("id", "Unknown"))
                tileset_id = tileset.get("id", "")
                click.echo(f"   - {name} ({tileset_id})")
            else:
                click.echo(f"   - {tileset}")

    except Exception as e:
        raise click.ClickException(str(e))


@main.command("delete-source")
@click.argument("source_id")
@click.option("--token", envvar="MAPBOX_ACCESS_TOKEN", help="Mapbox access token")
@click.option("--username", envvar="MAPBOX_USERNAME", help="Mapbox username")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_source(
    source_id: str,
    token: Optional[str],
    username: Optional[str],
    yes: bool,
) -> None:
    """Delete a tileset source."""
    if not yes:
        click.confirm(f"Are you sure you want to delete source '{source_id}'?", abort=True)

    try:
        uploader = TilesetUploader(access_token=token, username=username)
        if uploader.delete_source(source_id):
            click.echo(f"✅ Deleted source: {source_id}")
        else:
            click.echo(f"❌ Failed to delete source: {source_id}")
            sys.exit(1)

    except Exception as e:
        raise click.ClickException(str(e))


@main.command("delete-tileset")
@click.argument("tileset_id")
@click.option("--token", envvar="MAPBOX_ACCESS_TOKEN", help="Mapbox access token")
@click.option("--username", envvar="MAPBOX_USERNAME", help="Mapbox username")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_tileset(
    tileset_id: str,
    token: Optional[str],
    username: Optional[str],
    yes: bool,
) -> None:
    """Delete a tileset."""
    if not yes:
        click.confirm(f"Are you sure you want to delete tileset '{tileset_id}'?", abort=True)

    try:
        uploader = TilesetUploader(access_token=token, username=username)
        if uploader.delete_tileset(tileset_id):
            click.echo(f"✅ Deleted tileset: {tileset_id}")
        else:
            click.echo(f"❌ Failed to delete tileset: {tileset_id}")
            sys.exit(1)

    except Exception as e:
        raise click.ClickException(str(e))


if __name__ == "__main__":
    main()
