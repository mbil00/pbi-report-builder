"""Visual command package."""

from __future__ import annotations

from .app import visual_app, visual_arrange_app, visual_format_app, visual_sort_app

# Import submodules for command registration side effects.
from . import bindings as _bindings
from . import formatting as _formatting
from . import inspection as _inspection
from . import layout as _layout
from . import management as _management
from . import mutation as _mutation
from . import sorting as _sorting

__all__ = [
    "visual_app",
    "visual_arrange_app",
    "visual_format_app",
    "visual_sort_app",
]
