"""Hades II semantic Save result paging over the existing native-owned descriptors.

The physical descriptor id remains the mutation identity. Entity grouping is
only a read projection: pagination chooses complete entities before their
individual editable fields are returned to the Host.
"""


def _meaningful(value):
    return value is True or (
        value is not None and value is not False
        and (not isinstance(value, (int, float)) or value != 0)
        and (not isinstance(value, str) or bool(value))
    )


def entity_page(rows, *, search, offset, limit, aliases=None):
    """Filter/rank/page complete entities, never independent physical fields.

    aliases maps descriptor ids to native names from the other official locale.
    It is used only for lookup and is not sent as duplicate Save fields.
    """
    aliases = aliases or {}
    grouped = {}
    for row in rows:
        identity = row.get("entityId") or "entry:" + row["id"]
        title = row.get("entityName") or row["name"]
        if identity not in grouped:
            grouped[identity] = {
                "id": identity, "name": title, "items": [],
                "_terms": set(), "_populated": False, "_writable": False,
                "_browseReadOnly": False,
            }
        group = grouped[identity]
        group["items"].append(row)
        group["_populated"] |= _meaningful(row.get("value")) or bool(row.get("_browseReadOnly"))
        group["_writable"] |= bool(row.get("editable") and row.get("mutationKinds"))
        group["_browseReadOnly"] |= bool(row.get("_browseReadOnly"))
        group["_terms"].update(
            str(item).casefold() for item in (
                identity, title, row["id"], row["rawId"],
                row["name"], row["englishName"], *aliases.get(row["id"], ()),
                *row.get("_search", ())
            ) if item is not None
        )

    needle = search.strip().casefold()
    matches = []
    for group in grouped.values():
        if needle:
            if not any(needle in term for term in group["_terms"]):
                continue
        elif not group["_populated"] or not (group["_writable"] or group["_browseReadOnly"]):
            # Default browse favors present, actionable state. Deliberate
            # search still finds zero-valued and non-editable native records.
            continue
        primary = group["name"].casefold()
        if needle and primary == needle:
            relevance = 0
        elif needle and primary.startswith(needle):
            relevance = 1
        elif needle and needle in primary:
            relevance = 2
        elif needle and any(term.startswith(needle) for term in group["_terms"]):
            relevance = 3
        else:
            relevance = 4
        matches.append((relevance, primary, group["id"], group))
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    total = len(matches)
    # Offsets are entity counts. Projection of child fields happens only after
    # the result page has been selected.
    selected = [
        {"id": group["id"], "name": group["name"],
         "items": [{key: value for key, value in row.items() if not key.startswith("_")}
                   for row in group["items"]]}
        for _, _, _, group in matches[offset:offset + limit]
    ]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "hasMore": offset + len(selected) < total,
        "entities": selected,
    }
