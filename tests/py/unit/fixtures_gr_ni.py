"""Graphene on Ni(111), 1x1, carbons atop and over the hcp hollow (labels: 0 substrate, 1 film)."""
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
