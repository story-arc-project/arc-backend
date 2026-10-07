def parse_sort(sort: str, allowed_sort_fields: list[str]):
    if sort.startswith("-"):
        field = sort[1:]
        descending = True
    else:
        field = sort
        descending = False
    if field not in allowed_sort_fields:
        raise ValueError(f"Invalid sort field: {field}. Allowed fields: {allowed_sort_fields}")
    return field, descending