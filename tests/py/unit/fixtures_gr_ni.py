"""Graphene on Ni(111), 1x1, carbons atop and over the hcp hollow (labels: 0 substrate, 1 film)."""
from copy import deepcopy
from typing import Any, Dict

GRAPHENE_NICKEL_TOP_HCP: Dict[str, Any] = {
    "name": "C(001)-Ni(111), Interface",
    "basis": {
        "elements": [{"id": i, "value": e} for i, e in enumerate(["Ni", "Ni", "Ni", "C", "C"])],
        "coordinates": [
            {"id": 0, "value": [0, 0, 3.03e-7]},
            {"id": 1, "value": [0.666666667, 0.333333333, 0.100960811]},
            {"id": 2, "value": [0.333333333, 0.666666667, 0.201921319]},
            {"id": 3, "value": [0.333333333, 0.666666667, 0.351561882]},
            {"id": 4, "value": [0.666666667, 0.333333333, 0.351561882]},
        ],
        "labels": [{"id": i, "value": v} for i, v in enumerate([0, 0, 0, 1, 1])],
        "units": "crystal",
    },
    "lattice": {
        "a": 2.478974,
        "b": 2.478974,
        "c": 20.048173659,
        "alpha": 90,
        "beta": 90,
        "gamma": 120,
        "units": {"length": "angstrom", "angle": "degree"},
        "type": "HEX",
    },
}

# GRAPHENE_NICKEL_TOP_HCP with one carbon shifted 0.05 in fractional x, off its site: the only
# fixture with an in-plane force for a relaxation to constrain.
GRAPHENE_NICKEL_CARBON_DISPLACED: Dict[str, Any] = deepcopy(GRAPHENE_NICKEL_TOP_HCP)
GRAPHENE_NICKEL_CARBON_DISPLACED["basis"]["coordinates"][3]["value"][0] -= 0.05
