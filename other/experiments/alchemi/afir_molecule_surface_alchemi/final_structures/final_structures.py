# ---------------------------------------------------------------- #
#                                                                  #
#  Step 3, "Save Final Structures", of the workflow                #
#  "Molecule on Surface: AFIR Search (ALCHEMI)", a search with the #
#  artificial force induced reaction (AFIR) method.                #
#                                                                  #
#  Takes the lowest final structures of "Relax under AFIR Force    #
#  (ALCHEMI)", each with the configuration it started from, and    #
#  makes one request body per structure for the platform's         #
#  final-structure endpoint, which the io unit after this one      #
#  sends in a loop. Each request names this unit (UNIT_ID), so the #
#  structures are this step's results.                             #
#                                                                  #
#  Reads:  final_structures.extxyz and configurations.extxyz in    #
#          the job's work folder.                                  #
#  Writes: FINAL_STRUCTURE_REQUESTS to the job's global scope, as  #
#          the only output of the script.                          #
#                                                                  #
# ---------------------------------------------------------------- #

import json

from ase.io import read
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import from_ase


def request_body(rank_index, atoms, configurations):
    """
    Returns the body of one final-structure request, escaped to sit inside the next io unit's JSON string.

    The platform keeps one final_structure per unit and repetition, so each structure gets its own repetition.

    Args:
        rank_index (int): The structure's rank by final energy, from 0.
        atoms (ase.Atoms): The final structure, with its configuration's index in atoms.info.
        configurations (List[ase.Atoms]): All configurations, in the order of their indices.

    Returns:
        str: {"jobId", "unitId", "structures": [{"initial", "final"}]} as JSON, escaped for a JSON string.
    """
    final = {**Material.create(from_ase(atoms)).to_dict(), "repetition": rank_index}
    initial = Material.create(from_ase(configurations[atoms.info["configuration"]])).to_dict()
    body = {"jobId": "{{ JOB_ID }}", "unitId": "{{ UNIT_ID }}", "structures": [{"initial": initial, "final": final}]}
    return json.dumps(json.dumps(body))[1:-1]


def main():
    """
    Reads the lowest final structures and the configurations, and prints the request bodies as
    FINAL_STRUCTURE_REQUESTS.
    """
    final_structures = read("{{ JOB_WORK_DIR }}/final_structures.extxyz", index=":")
    configurations = read("{{ JOB_WORK_DIR }}/configurations.extxyz", index=":")
    request_bodies = [request_body(rank_index, atoms, configurations)
                      for rank_index, atoms in enumerate(final_structures)]
    print(json.dumps({"name": "FINAL_STRUCTURE_REQUESTS", "value": request_bodies, "scope": "global"}))


if __name__ == "__main__":
    main()
