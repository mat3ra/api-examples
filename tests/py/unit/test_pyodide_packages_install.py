from mat3ra.notebooks_utils.pyodide.packages.install import should_reinstall_package


def test_reinstalls_only_when_the_same_package_version_changes():
    previous = ["networkx==3.2.1", "scipy==1.11.2"]

    assert should_reinstall_package("networkx==3.2.2", previous)
    assert not should_reinstall_package("networkx==3.2.1", previous)
    assert not should_reinstall_package("tabulate==0.9.0", previous)


def test_does_not_reinstall_url_or_emfs_requirements():
    assert not should_reinstall_package(
        "emfs:/drive/packages/example.whl",
        ["emfs:/drive/packages/old.whl"],
    )
