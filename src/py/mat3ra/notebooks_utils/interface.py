from typing import Dict, Optional


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
