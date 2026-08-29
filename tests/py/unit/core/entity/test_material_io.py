from unittest.mock import patch

from mat3ra.made.material import Material
from mat3ra.notebooks_utils.core.entity.material.io import sync_materials
from mat3ra.standata.materials import Materials


def material(name: str) -> Material:
    return Material.create({**Materials.get_by_name_first_match("Silicon"), "name": name})


def test_sync_materials_collects_public_bindings_and_one_container_level():
    direct = material("direct")
    listed = material("listed")
    mapped = material("mapped")

    namespace = {
        "direct": direct,
        "group": [listed, 3, [material("too-deep")]],
        "mapping": {"value": mapped},
        "materials_in": [material("input")],
        "material": material("selected"),
        "_private": material("private"),
        "number": 4,
    }

    with patch("mat3ra.notebooks_utils.core.entity.material.io.send_data") as send:
        sync_materials(namespace)

    payload = send.call_args.args[0]
    assert payload["syncScope"] == "python-repl"
    assert [(entity["type"], entity["name"]) for entity in payload["entities"]] == [
        ("material", "direct"),
        ("material", "group"),
        ("material", "mapping"),
    ]
    assert [entity["config"]["name"] for entity in payload["entities"]] == [
        "direct",
        "listed",
        "mapped",
    ]


def test_sync_materials_sends_an_empty_batch_to_clear_the_scope():
    with patch("mat3ra.notebooks_utils.core.entity.material.io.send_data") as send:
        sync_materials({"x": 1}, sync_scope="test-scope")

    send.assert_called_once_with({"syncScope": "test-scope", "entities": []})
