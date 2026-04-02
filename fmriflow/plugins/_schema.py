"""PARAM_SCHEMA type definitions and extraction utilities."""

from __future__ import annotations

from typing import Any, TypedDict


class ParamField(TypedDict, total=False):
    """Schema for a single plugin parameter."""
    type: str           # "int" | "float" | "bool" | "string" | "path"
                        # | "list[int]" | "list[string]" | "dict"
    default: Any        # Default value (None if required)
    required: bool      # Whether the field is required (default False)
    min: float          # Minimum value (numeric types)
    max: float          # Maximum value (numeric types)
    enum: list          # Allowed values
    description: str    # Human-readable description


ParamSchema = dict[str, ParamField]


def extract_schema(cls) -> ParamSchema:
    """Extract PARAM_SCHEMA from a plugin class, falling back to empty."""
    return getattr(cls, 'PARAM_SCHEMA', {})


def schema_defaults(schema: ParamSchema) -> dict[str, Any]:
    """Return {param_name: default_value} for all params with defaults."""
    return {
        name: field['default']
        for name, field in schema.items()
        if 'default' in field
    }
