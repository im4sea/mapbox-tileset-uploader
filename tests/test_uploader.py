"""Tests for the uploader module."""

import os
import pytest
from unittest.mock import patch, MagicMock

from mapbox_tileset_uploader.uploader import TilesetConfig, TilesetUploader


class TestTilesetConfig:
    """Test TilesetConfig dataclass."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = TilesetConfig(
            tileset_id="test-tileset",
            tileset_name="Test Tileset",
        )

        assert config.tileset_id == "test-tileset"
        assert config.tileset_name == "Test Tileset"
        assert config.source_id == "test-tileset"
        assert config.layer_name == "data"
        assert config.min_zoom == 0
        assert config.max_zoom == 10

    def test_source_id_default(self) -> None:
        """Test that source_id defaults to tileset_id with dots replaced."""
        config = TilesetConfig(
            tileset_id="my.test.tileset",
            tileset_name="Test",
        )

        assert config.source_id == "my-test-tileset"

    def test_custom_source_id(self) -> None:
        """Test custom source_id."""
        config = TilesetConfig(
            tileset_id="test",
            tileset_name="Test",
            source_id="custom-source",
        )

        assert config.source_id == "custom-source"


class TestTilesetUploader:
    """Test TilesetUploader class."""

    def test_missing_token(self) -> None:
        """Test error when token is missing."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MAPBOX_ACCESS_TOKEN", None)
            os.environ.pop("MAPBOX_USERNAME", None)

            with pytest.raises(ValueError, match="access token required"):
                TilesetUploader()

    def test_missing_username(self) -> None:
        """Test error when username is missing."""
        with patch.dict(os.environ, {"MAPBOX_ACCESS_TOKEN": "test-token"}, clear=True):
            os.environ.pop("MAPBOX_USERNAME", None)

            with pytest.raises(ValueError, match="username required"):
                TilesetUploader(access_token="test-token")

    def test_credentials_from_env(self) -> None:
        """Test credentials from environment variables."""
        with patch.dict(
            os.environ,
            {"MAPBOX_ACCESS_TOKEN": "env-token", "MAPBOX_USERNAME": "env-user"},
        ):
            uploader = TilesetUploader()

            assert uploader.access_token == "env-token"
            assert uploader.username == "env-user"

    def test_credentials_from_params(self) -> None:
        """Test credentials from parameters override env."""
        with patch.dict(
            os.environ,
            {"MAPBOX_ACCESS_TOKEN": "env-token", "MAPBOX_USERNAME": "env-user"},
        ):
            uploader = TilesetUploader(
                access_token="param-token",
                username="param-user",
            )

            assert uploader.access_token == "param-token"
            assert uploader.username == "param-user"

    def test_build_recipe(self) -> None:
        """Test recipe building."""
        with patch.dict(
            os.environ,
            {"MAPBOX_ACCESS_TOKEN": "test", "MAPBOX_USERNAME": "testuser"},
        ):
            uploader = TilesetUploader()
            config = TilesetConfig(
                tileset_id="test",
                tileset_name="Test",
                source_id="test-source",
                layer_name="mylayer",
                min_zoom=2,
                max_zoom=14,
            )

            recipe = uploader._build_recipe(config)

            assert recipe["version"] == 1
            assert "mylayer" in recipe["layers"]
            assert recipe["layers"]["mylayer"]["minzoom"] == 2
            assert recipe["layers"]["mylayer"]["maxzoom"] == 14

    def test_custom_recipe(self) -> None:
        """Test that custom recipe is used when provided."""
        with patch.dict(
            os.environ,
            {"MAPBOX_ACCESS_TOKEN": "test", "MAPBOX_USERNAME": "testuser"},
        ):
            uploader = TilesetUploader()
            custom = {"version": 1, "layers": {"custom": {"source": "test"}}}
            config = TilesetConfig(
                tileset_id="test",
                tileset_name="Test",
                recipe=custom,
            )

            recipe = uploader._build_recipe(config)

            assert recipe == custom
