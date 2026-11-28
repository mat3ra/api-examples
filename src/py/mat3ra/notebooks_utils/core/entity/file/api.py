from mat3ra.wode.units.io import to_object_storage_input as _to_object_storage_input


def to_object_storage_input(cloud_file: dict) -> dict:
    """
    `to_object_storage_input` of mat3ra.wode.units.io, returning the IO unit input item as a dict.
    """
    return _to_object_storage_input(cloud_file).model_dump(exclude_none=True)
