"""Imports exposed by the Materials Designer Python REPL."""

from mat3ra.made.material import Material
from mat3ra.made.tools.build.defective_structures.zero_dimensional.point_defect import (
    AtomPlacementMethodEnum,
    InterstitialPlacementMethodEnum,
    PointDefectTypeEnum,
    SubstitutionPlacementMethodEnum,
    VacancyPlacementMethodEnum,
)
from mat3ra.made.tools.build.pristine_structures.zero_dimensional.nanoparticle.enums import NanoparticleShapesEnum
from mat3ra.made.tools.build_components.entities.reusable.zero_dimensional.coordinates_shape_enum import (
    CoordinatesShapeEnum,
)
from mat3ra.made.tools.helpers import *  # noqa: F403
from mat3ra.made.tools.helpers import __all__ as _HELPER_NAMES

# Each `create_defect_point_*` helper accepts only a subset of AtomPlacementMethodEnum and rejects
# anything else with a bare "Unsupported placement method". Exposing the per-defect enums lets the
# REPL's completions show which subset applies at the call site, instead of leaving the caller to
# guess a string.
__all__ = [
    "AtomPlacementMethodEnum",
    "CoordinatesShapeEnum",
    "InterstitialPlacementMethodEnum",
    "Material",
    "NanoparticleShapesEnum",
    "PointDefectTypeEnum",
    "SubstitutionPlacementMethodEnum",
    "VacancyPlacementMethodEnum",
    *_HELPER_NAMES,
]
