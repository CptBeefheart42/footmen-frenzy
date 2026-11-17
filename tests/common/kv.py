"""The `key=value` fields the map's rows are made of."""


def parse_kv(fields):
    """Collects the `key=value` fields of a split row.

    Args:
        fields: The row's fields (already split at the commas). Fields without `=` are skipped.

    Returns:
        A dict of key to value (both strings). A key that appears twice keeps its last value.
    """
    out = {}
    for f in fields:
        k, eq, v = f.partition("=")
        if eq:
            out[k] = v
    return out


def as_int(value):
    """Reads an integer field.

    Args:
        value: The field's text, or None.

    Returns:
        The integer, or None when the value is missing or not an integer.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
