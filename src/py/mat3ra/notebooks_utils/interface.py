from typing import Dict, Optional, Set, Tuple

from mat3ra.made.material import Material
from mat3ra.made.tools.helpers import get_film_site_occupation


def film_sites_and_buckling(interface: Material) -> Tuple[Set[Optional[str]], Optional[float]]:
    """
    The named sites the film's atoms occupy, and the atop atom's height above the others (None
    when no atom is atop -- then there is no reference atom to sign the buckling against).

    Args:
        interface (Material): The interface, film and substrate labelled.

    Returns:
        Tuple[Set[Optional[str]], Optional[float]]: Occupied site names, and the buckling in the
        material's length units.
    """
    occupied = get_film_site_occupation(interface)
    cartesian = interface.clone()
    cartesian.to_cartesian()
    heights = {i: cartesian.coordinates_array[i][2] for i in occupied}
    atop = [i for i, site in occupied.items() if site == "atop"]
    buckling = None if not atop else float(heights[atop[0]] - next(z for i, z in heights.items() if i != atop[0]))
    return set(occupied.values()), buckling


def buckling_text(buckling: Optional[float]) -> str:
    """Format a signed buckling value for a registry table row, or a dash when there is none."""
    return "   —   " if buckling is None else f"{buckling:+.3f}"


def registry_cell(label: str, result: Dict) -> str:
    """
    The registry column for a results table: the nominal label, or the label plus the sites
    actually reached when the job drifted -- so a drifted row is never mistaken for its nominal
    registry's result.

    Args:
        label (str): The nominal registry name.
        result (Dict): Must carry "drifted" (bool) and, when drifted, "sites" (an iterable of the
            site names actually reached).
    """
    if not result["drifted"]:
        return label
    sites = "/".join(sorted(str(site) for site in result["sites"]))
    return f"{label}→{sites}"
