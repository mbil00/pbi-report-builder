"""Semantic-model CLI command package."""

from __future__ import annotations

from .base import (
    model_app,
    model_annotation_app,
    model_column_app,
    model_field_parameter_app,
    model_hierarchy_app,
    model_measure_app,
    model_partition_app,
    model_perspective_app,
    model_role_app,
    model_relationship_app,
    model_table_app,
)
import pbi.commands.model.annotations as _model_annotations
from . import columns as _columns
from . import field_parameters as _field_parameters
from . import hierarchies as _hierarchies
from . import inspection as _inspection
from . import measures as _measures
from . import partitions as _partitions
from . import perspectives as _perspectives
from . import roles as _roles
from . import relationships as _relationships
from . import tables as _tables

__all__ = [
    "model_app",
    "model_annotation_app",
    "model_column_app",
    "model_field_parameter_app",
    "model_hierarchy_app",
    "model_measure_app",
    "model_partition_app",
    "model_perspective_app",
    "model_role_app",
    "model_relationship_app",
    "model_table_app",
]
