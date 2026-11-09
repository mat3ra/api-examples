# ---------------------------------------------------------------- #
#                                                                  #
#  Step 1, "Create Initial Configurations", of the workflow        #
#  "Molecule on Surface: AFIR Search (ALCHEMI)", a search with the #
#  artificial force induced reaction (AFIR) method.                #
#                                                                  #
#  Places the job's molecule over its slab                         #
#  NUMBER_OF_CONFIGURATIONS times with made, each at a random      #
#  orientation and a random point of the surface cell, as          #
#  GRRM17's random initial structures [1].                         #
#                                                                  #
#  Reads:  the job's two materials, written into this script by    #
#          the platform when the job is created; the non-periodic  #
#          one is the molecule.                                    #
#  Writes: configurations.extxyz in the job's work folder: the     #
#          placed structures, slab atoms tagged 0 and molecule     #
#          atoms 1, each with its index in the info key            #
#          configuration and its rotation and fractional position  #
#          in metadata.placement. It is the only output of the     #
#          script.                                                 #
#                                                                  #
#  [1] S. Maeda et al., J. Comput. Chem. 39, 233 (2018).           #
#                                                                  #
# ---------------------------------------------------------------- #

import json

import numpy as np
from ase.data import atomic_numbers, covalent_radii
from ase.io import write
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import to_ase
from mat3ra.made.tools.convert.interface_parts_enum import InterfacePartsEnum
from mat3ra.made.tools.modify import translate_by_vector
from mat3ra.made.tools.operations.core.binary import merge
from mat3ra.made.tools.operations.core.unary import rotate

NUMBER_OF_CONFIGURATIONS = 100
RANDOM_SEED = 0
CONTACT_OFFSET = 0.5  # Å, lowest molecule atom at R_molecule + R_slab + CONTACT_OFFSET above the top slab atom
# The job's materials, written here by the platform when the job is created.
MATERIALS = json.loads(r"""{{ materials | dump | safe }}""")


def extreme_atom_height_and_radius(material, extremum):
    """
    Returns the height and the covalent radius of the highest or the lowest atom of a material.

    Args:
        material (Material): The material to search.
        extremum (Callable): max for the highest atom, min for the lowest.

    Returns:
        Tuple[float, float]: The atom's cartesian z and its covalent radius, both in Å.
    """
    cartesian = material.clone()
    cartesian.to_cartesian()
    height, element = extremum(zip([coordinate[2] for coordinate in cartesian.basis.coordinates.values],
                                   cartesian.basis.elements.values))
    return height, covalent_radii[atomic_numbers[element]]


def create_configuration(slab, molecule, top_atom_height_and_radius, random_generator, index):
    """
    Places the molecule once over the slab, as a random initial structure of GRRM17's MC-AFIR.

    The orientation is uniformly random (a normalised Gaussian quaternion), the molecule's center goes to a random
    point of the surface cell, and its lowest atom sits R_molecule + R_slab + CONTACT_OFFSET above the top slab atom,
    the RandDC rule of GRRM17 (S. Maeda et al., J. Comput. Chem. 39, 233 (2018)).

    Args:
        slab (Material): The slab, in crystal units, labelled 0.
        molecule (Material): The molecule, in crystal units.
        top_atom_height_and_radius (Tuple[float, float]): Height and covalent radius of the top slab atom, in Å.
        random_generator (numpy.random.Generator): The seeded generator of all placements.
        index (int): The configuration's index, used in its name.

    Returns:
        MaterialWithBuildMetadata: The slab and the placed molecule, molecule atoms labelled 1, with the rotation and
        the fractional position in metadata.placement.
    """
    quaternion = random_generator.normal(size=4)
    axis = (quaternion[1:] / np.linalg.norm(quaternion[1:])).tolist()
    angle = float(2 * np.degrees(np.arccos(quaternion[0] / np.linalg.norm(quaternion))))
    rotated = rotate(molecule, axis=axis, angle=angle, wrap=False)
    rotated.set_lattice(slab.lattice)
    top_height, top_radius = top_atom_height_and_radius
    lowest_height, lowest_radius = extreme_atom_height_and_radius(rotated, min)
    surface_fractions = [random_generator.random(), random_generator.random(), 0]
    surface_point = slab.basis.cell.convert_point_to_cartesian(surface_fractions)
    molecule_cell_center = molecule.basis.cell.convert_point_to_cartesian([0.5, 0.5, 0.5])
    vertical_shift = top_height + top_radius + lowest_radius + CONTACT_OFFSET - lowest_height
    placed = translate_by_vector(rotated, vector=[surface_point[0] - molecule_cell_center[0],
                                                  surface_point[1] - molecule_cell_center[1], vertical_shift],
                                 use_cartesian_coordinates=True)
    placed.set_labels_from_value(InterfacePartsEnum.FILM.value)
    configuration = merge([slab, placed], material_name=f"{molecule.name} on {slab.name}, configuration {index}")
    configuration.metadata.placement = {"rotation_axis": axis, "rotation_angle_deg": angle,
                                        "position": surface_fractions[:2]}
    return configuration


def main():
    """
    Builds NUMBER_OF_CONFIGURATIONS configurations from the job's materials and writes them to configurations.extxyz.
    """
    slab = Material.create(next(material_config for material_config in MATERIALS
                                if not material_config.get("isNonPeriodic")))
    molecule = Material.create(next(material_config for material_config in MATERIALS
                                    if material_config.get("isNonPeriodic")))
    for material in (slab, molecule):
        material.to_crystal()
    slab.set_labels_from_value(InterfacePartsEnum.SUBSTRATE.value)
    top_atom_height_and_radius = extreme_atom_height_and_radius(slab, max)
    random_generator = np.random.default_rng(RANDOM_SEED)
    configurations = []
    for index in range(NUMBER_OF_CONFIGURATIONS):
        atoms = to_ase(create_configuration(slab, molecule, top_atom_height_and_radius, random_generator, index))
        atoms.info["configuration"] = index
        configurations.append(atoms)
    write("configurations.extxyz", configurations)


if __name__ == "__main__":
    main()
