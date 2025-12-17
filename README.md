# Mapbox Tileset Uploader

A CLI tool and Python library to upload GeoJSON and TopoJSON files to Mapbox as vector tilesets.

[![PyPI version](https://badge.fury.io/py/mapbox-tileset-uploader.svg)](https://badge.fury.io/py/mapbox-tileset-uploader)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 📤 Upload GeoJSON and TopoJSON files to Mapbox Tiling Service (MTS)
- 🌐 Download and upload from remote URLs
- 🔄 Automatic TopoJSON to GeoJSON conversion
- ⚙️ Configurable zoom levels, layer names, and recipes
- 🔧 Both CLI and Python API available
- 📦 Installable via pip

## Installation

```bash
pip install mapbox-tileset-uploader
```

Or install from source:

```bash
git clone https://github.com/maplumi/mapbox-tileset-uploader.git
cd mapbox-tileset-uploader
pip install -e .
```

## Prerequisites

1. **Mapbox Account**: Sign up at [mapbox.com](https://www.mapbox.com/)
2. **Access Token**: Create a token with the following scopes:
   - `tilesets:write`
   - `tilesets:read`
   - `tilesets:list`

Set your credentials as environment variables:

```bash
export MAPBOX_ACCESS_TOKEN="your-token-here"
export MAPBOX_USERNAME="your-username"
```

## CLI Usage

The package provides two command aliases: `mapbox-tileset-uploader` and `mtu` (short form).

### Upload from URL

```bash
mtu upload \
  --url https://example.com/data.geojson \
  --id my-tileset \
  --name "My Tileset"
```

### Upload from Local File

```bash
mtu upload \
  --file data.geojson \
  --id my-tileset \
  --name "My Tileset"
```

### Upload with Custom Options

```bash
mtu upload \
  --file data.topojson \
  --id boundaries-adm1 \
  --name "Administrative Boundaries Level 1" \
  --layer boundaries \
  --min-zoom 2 \
  --max-zoom 12 \
  --description "Admin level 1 boundaries" \
  --attribution "© OpenStreetMap contributors"
```

### Convert TopoJSON to GeoJSON

```bash
mtu convert input.topojson output.geojson --pretty
```

### List Resources

```bash
# List all tileset sources
mtu list-sources

# List all tilesets
mtu list-tilesets
```

### Delete Resources

```bash
# Delete a tileset source
mtu delete-source my-source-id

# Delete a tileset
mtu delete-tileset my-tileset-id
```

### Dry Run Mode

Validate your file without uploading:

```bash
mtu upload --file data.geojson --id test --name "Test" --dry-run
```

## Python API Usage

```python
from mapbox_tileset_uploader import TilesetUploader
from mapbox_tileset_uploader.uploader import TilesetConfig

# Initialize uploader (uses environment variables by default)
uploader = TilesetUploader()

# Or provide credentials explicitly
uploader = TilesetUploader(
    access_token="your-token",
    username="your-username"
)

# Configure the tileset
config = TilesetConfig(
    tileset_id="my-tileset",
    tileset_name="My Tileset",
    layer_name="data",
    min_zoom=0,
    max_zoom=10,
    description="My geographic data"
)

# Upload from URL
results = uploader.upload_from_url(
    url="https://example.com/data.geojson",
    config=config
)

# Upload from local file
results = uploader.upload_from_file(
    file_path="data.geojson",
    config=config
)

if results["success"]:
    print(f"Tileset uploaded: {results['tileset_id']}")
else:
    print(f"Error: {results.get('error')}")
```

### TopoJSON Conversion

```python
from mapbox_tileset_uploader import convert_topojson_to_geojson

# From dictionary
topojson_data = {...}
geojson = convert_topojson_to_geojson(topojson_data)

# From file
from mapbox_tileset_uploader.converter import load_and_convert
geojson = load_and_convert("data.topojson")
```

## Custom Recipes

For advanced configurations, provide a custom MTS recipe:

```bash
mtu upload \
  --file data.geojson \
  --id my-tileset \
  --name "My Tileset" \
  --recipe custom-recipe.json
```

Recipe file example (`custom-recipe.json`):

```json
{
  "version": 1,
  "layers": {
    "boundaries": {
      "source": "mapbox://tileset-source/{username}/{source-id}",
      "minzoom": 0,
      "maxzoom": 14,
      "features": {
        "simplify": {
          "outward_only": true,
          "distance": 1
        }
      }
    }
  }
}
```

## GitHub Actions Integration

Use in your CI/CD pipeline:

```yaml
name: Upload Tilesets

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  upload:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install mapbox-tileset-uploader

      - name: Upload tileset
        env:
          MAPBOX_ACCESS_TOKEN: ${{ secrets.MAPBOX_ACCESS_TOKEN }}
          MAPBOX_USERNAME: ${{ secrets.MAPBOX_USERNAME }}
        run: |
          mtu upload \
            --file data.geojson \
            --id my-tileset \
            --name "My Tileset"
```

## Development

### Setup

```bash
git clone https://github.com/maplumi/mapbox-tileset-uploader.git
cd mapbox-tileset-uploader
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

### Code Formatting

```bash
black src tests
ruff check src tests
```

### Type Checking

```bash
mypy src
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Related Projects

- [mapbox-tilesets](https://github.com/mapbox/tilesets-cli) - Official Mapbox Tilesets CLI
- [geoBoundaries](https://www.geoboundaries.org/) - Open political boundary data
