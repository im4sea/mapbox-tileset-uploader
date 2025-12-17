"""
Converter registry for auto-detecting and loading format converters.
"""

from pathlib import Path
from typing import Any

from mapbox_tileset_uploader.converters.base import BaseConverter


class ConverterRegistry:
    """
    Registry for GIS format converters.

    Provides auto-detection of file formats and lazy loading of converters.
    """

    _converters: dict[str, type[BaseConverter]] = {}
    _extension_map: dict[str, str] = {}

    @classmethod
    def register(cls, converter_class: type[BaseConverter]) -> type[BaseConverter]:
        """
        Register a converter class.

        Can be used as a decorator:
            @ConverterRegistry.register
            class MyConverter(BaseConverter):
                ...

        Args:
            converter_class: The converter class to register.

        Returns:
            The same converter class (for decorator use).
        """
        format_name = converter_class.format_name.lower()
        cls._converters[format_name] = converter_class

        for ext in converter_class.file_extensions:
            cls._extension_map[ext.lower()] = format_name

        return converter_class

    @classmethod
    def get_converter(
        cls,
        format_name: str | None = None,
        file_path: str | Path | None = None,
    ) -> BaseConverter:
        """
        Get a converter instance by format name or file path.

        Args:
            format_name: Explicit format name (e.g., "shapefile", "geojson").
            file_path: File path to auto-detect format from.

        Returns:
            Instantiated converter.

        Raises:
            ValueError: If format cannot be determined or is not supported.
        """
        if format_name:
            name = format_name.lower()
            if name not in cls._converters:
                raise ValueError(
                    f"Unknown format: {format_name}. Supported: {', '.join(cls._converters.keys())}"
                )
            return cls._converters[name]()

        if file_path:
            path = Path(file_path)
            suffix = path.suffix.lower()

            # Handle compound extensions
            if suffix in (".gz", ".zip"):
                suffix = "".join(path.suffixes[-2:]).lower()

            if suffix not in cls._extension_map:
                raise ValueError(
                    f"Unknown file extension: {suffix}. "
                    f"Supported: {', '.join(cls._extension_map.keys())}"
                )

            format_name = cls._extension_map[suffix]
            return cls._converters[format_name]()

        raise ValueError("Either format_name or file_path must be provided")

    @classmethod
    def get_supported_formats(cls) -> list[dict[str, Any]]:
        """
        Get information about all registered converters.

        Returns:
            List of converter info dictionaries.
        """
        result = []
        for name, converter_class in sorted(cls._converters.items()):
            info = converter_class.get_info()
            info["available"] = cls._is_available(converter_class)
            result.append(info)
        return result

    @classmethod
    def _is_available(cls, converter_class: type[BaseConverter]) -> bool:
        """Check if a converter's dependencies are installed."""
        for package in converter_class.requires_packages:
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                return False
        return True

    @classmethod
    def is_supported(cls, file_path: str | Path) -> bool:
        """
        Check if a file format is supported.

        Args:
            file_path: Path to check.

        Returns:
            True if the format is supported.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix in (".gz", ".zip"):
            suffix = "".join(path.suffixes[-2:]).lower()
        return suffix in cls._extension_map


# Convenience functions
def get_converter(
    format_name: str | None = None,
    file_path: str | Path | None = None,
) -> BaseConverter:
    """Get a converter instance. See ConverterRegistry.get_converter."""
    return ConverterRegistry.get_converter(format_name, file_path)


def get_supported_formats() -> list[dict[str, Any]]:
    """Get supported formats. See ConverterRegistry.get_supported_formats."""
    return ConverterRegistry.get_supported_formats()


def register_converter(converter_class: type[BaseConverter]) -> type[BaseConverter]:
    """Register a converter. See ConverterRegistry.register."""
    return ConverterRegistry.register(converter_class)


def _register_builtin_converters() -> None:
    """Register all built-in converters."""
    # Import converters to trigger registration
    from mapbox_tileset_uploader.converters import (
        geojson,  # noqa: F401
        topojson,  # noqa: F401
    )

    # Optional converters - only register if dependencies available
    try:
        from mapbox_tileset_uploader.converters import shapefile  # noqa: F401
    except ImportError:
        pass

    try:
        from mapbox_tileset_uploader.converters import geopackage  # noqa: F401
    except ImportError:
        pass

    try:
        from mapbox_tileset_uploader.converters import kml  # noqa: F401
    except ImportError:
        pass

    try:
        from mapbox_tileset_uploader.converters import flatgeobuf  # noqa: F401
    except ImportError:
        pass

    try:
        from mapbox_tileset_uploader.converters import geoparquet  # noqa: F401
    except ImportError:
        pass

    try:
        from mapbox_tileset_uploader.converters import gpx  # noqa: F401
    except ImportError:
        pass


# Register built-in converters on module load
_register_builtin_converters()
