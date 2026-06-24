import io
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import ipywidgets as widgets
from ase.build import make_supercell
from ase.io import write
from IPython.display import HTML, Javascript, display
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import to_ase
from mat3ra.utils.array import convert_to_array_if_not

from ...ui import MaterialViewProperties, create_responsive_image_grid, get_viewer_html, get_viewer_js


class ViewersEnum(str, Enum):
    wave = "wave"
    ase = "ase"


def get_material_image(material: Material, title: str, rotation="0x,0y,0z", repetitions=[1, 1, 1]):
    """
    Returns an image of the material structure with the specified title.

    Args:
        material (Material): Material object to visualize.
        title (str): Title of the image.
        rotation (str): Rotation of the image.
        repetitions (list): Repetitions alongside a,b,c lattice vectors.

    Returns:
        tuple: Tuple containing the image bytes and the title.
    """
    ase_atoms = to_ase(material)
    supercell_matrix = [[repetitions[0], 0, 0], [0, repetitions[1], 0], [0, 0, repetitions[2]]]
    material_repeat = make_supercell(ase_atoms, supercell_matrix)
    text = f"{ase_atoms.get_chemical_formula()} - {title} - rotation: {rotation}"

    buf = io.BytesIO()
    write(buf, material_repeat, format="png", rotation=rotation)
    buf.seek(0)
    return buf.read(), text


def get_wave_viewer(material, div_id, width, height, title):
    size = min(width, height)
    html = get_viewer_html(
        div_id=div_id,
        width=size,
        height=size,
        title=title,
        custom_styles="border:1px solid #333;",
    )
    js = get_viewer_js(
        data_json=material.to_json(),
        div_id=div_id,
        bundle_url="https://mat3ra.github.io/wave.js/main.js",
        render_function="renderThreeDEditor",
        data_var_name="materialConfig",
        css_url="https://mat3ra.github.io/wave.js/main.css",
    )
    return html, js


def render_wave(material, properties, width=600, height=600):
    timestamp = time.time()
    div_id = f"wave-{timestamp}"
    html, js = get_wave_viewer(material, div_id, width, height, properties.title)
    display(HTML(html))
    display(Javascript(js))


def render_wave_grid(
    materials: List[Material],
    list_of_properties_configs: List[MaterialViewProperties],
    width=400,
    height=400,
    max_columns=3,
):
    html_items = []
    js_items = []
    timestamp = time.time()

    for i, material in enumerate(materials):
        properties_config = list_of_properties_configs[i]
        div_id = f"wave-{i}-{timestamp}"
        html, js = get_wave_viewer(material, div_id, width, height, properties_config.title)
        html_items.append(widgets.HTML(html))
        js_items.append(Javascript(js))

    grid = widgets.GridBox(
        html_items,
        layout=widgets.Layout(
            grid_template_columns=f"repeat({max_columns}, 1fr)",
            grid_gap="10px",
            width="100%",
        ),
    )
    display(grid)
    for js in js_items:
        display(js)


def _process_material_entry(
    material_entry: Union[Material, Dict], default_properties: MaterialViewProperties
) -> Tuple[Material, MaterialViewProperties]:
    """
    Process the material entry and return the material and properties.

    Args:
        material_entry: Material or a dictionary containing the material and properties.
        default_properties: Default properties to use if not specified in the material entry.

    Returns:
        Tuple[Material, MaterialViewProperties]: Material and properties.
    """
    if isinstance(material_entry, Material):
        material = material_entry
        properties = default_properties
    elif isinstance(material_entry, dict) and "material" in material_entry:
        material = material_entry["material"]
        properties = MaterialViewProperties(
            title=material_entry.get("title", default_properties.title),
            repetitions=material_entry.get("repetitions", default_properties.repetitions),
            rotation=material_entry.get("rotation", default_properties.rotation),
        )
    else:
        raise ValueError("Invalid material entry")
    return material, properties


def visualize_materials(
    materials: Union[List[Material], List[Dict[str, Union[Material, dict]]]],
    repetitions: Optional[List[int]] = [1, 1, 1],
    rotation: Optional[str] = "0x,0y,0z",
    title: Optional[str] = "Material",
    viewer: ViewersEnum = ViewersEnum.ase,
) -> None:
    """
    Visualize the material(s) in the output cell.

    Args:
        materials: List of Materials or list of dicts with "material", "title", "repetitions", "rotation".
        repetitions (Optional[List[int]]): Repetitions alongside a, b, c lattice vectors.
        rotation (Optional[str]): Rotation of the image.
        title (Optional[str]): Title of the image.
        viewer (ViewersEnum): Viewer to use for visualization. "ase" or "wave".
    """
    materials = convert_to_array_if_not(materials)

    if not materials:
        print("No materials to visualize.")
        return

    default_properties = MaterialViewProperties(
        title=title if title is not None else MaterialViewProperties.title,
        repetitions=repetitions if repetitions is not None else MaterialViewProperties.repetitions,
        rotation=rotation if rotation is not None else MaterialViewProperties.rotation,
    )

    if viewer == ViewersEnum.wave:
        wave_materials = []
        wave_properties_list = []
        for material_entry in materials:
            material, material_properties = _process_material_entry(material_entry, default_properties)
            wave_materials.append(material)
            wave_properties_list.append(material_properties)
        if len(wave_materials) == 1:
            render_wave(wave_materials[0], properties=wave_properties_list[0])
        else:
            render_wave_grid(materials=wave_materials, list_of_properties_configs=wave_properties_list)

    else:
        items = []
        for material_entry in materials:
            material, properties = _process_material_entry(material_entry, default_properties)
            if material:
                image_data, image_title = get_material_image(
                    material, title=properties.title, rotation=properties.rotation, repetitions=properties.repetitions
                )
                items.append((image_data, image_title))

        display(create_responsive_image_grid(items))
