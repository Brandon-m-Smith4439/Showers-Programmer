"""Pure production-rule helpers for Shower Programmer.

Keep deterministic policy here so GUI/workflow code can call the same tested rules
without duplicating business logic.  Larger geometry operations remain in the
programming core and are migrated into this package incrementally.
"""

from .archive import ordered_unique_paths
from .dimensions import dimensions_match
from .indicators import indicator_summary
from .machine import minimum_dimension_forces_waterjet
from .orientation import default_machine_rotation
from .remake import location_value_indicates_remake, pdf_location_indicates_remake, pdf_location_values

__all__ = [
    "default_machine_rotation",
    "dimensions_match",
    "indicator_summary",
    "location_value_indicates_remake",
    "minimum_dimension_forces_waterjet",
    "ordered_unique_paths",
    "pdf_location_indicates_remake",
    "pdf_location_values",
]
