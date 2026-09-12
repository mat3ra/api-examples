import pytest
from mat3ra.made.material import Material
from mat3ra.made.tools.convert.interface_parts_enum import InterfacePartsEnum
from mat3ra.notebooks_utils.material import label_interface_parts
from mat3ra.standata.materials import Materials

TIN = Material.create(Materials.get_by_name_first_match("Titanium_Nitride"))


@pytest.mark.parametrize(
    ("substrate_elements", "expected_labels"),
    [
        ({"Ti"}, [InterfacePartsEnum.SUBSTRATE.value] * 4 + [InterfacePartsEnum.FILM.value] * 4),
        ({"N"}, [InterfacePartsEnum.FILM.value] * 4 + [InterfacePartsEnum.SUBSTRATE.value] * 4),
    ],
)
def test_label_interface_parts(substrate_elements, expected_labels):
    material = TIN.clone()
    label_interface_parts(material, substrate_elements)
    assert material.basis.labels.values == expected_labels
