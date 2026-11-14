"""Cursor support for legacy single-document patient fixtures.

A fixture's find_one still defines its stored documents. Identity lookup probes
all BSON ID candidates and retains only exact matches, including distinct BSON
and string IDs; other queries retain the fixture's existing cursor behavior.
"""
from copy import deepcopy
from unittest.mock import AsyncMock


def legacy_domain_state(db):
    """Pin an in-memory db fixture to the legacy patient domain (no state doc).

    MagicMock-style doubles auto-create unconfigured attribute chains, whose
    find_one is not awaitable. Declaring the state read explicitly simulates the
    "no patient_domain_state document => legacy domain" production semantics.
    """
    db.patient_domain_state.find_one = AsyncMock(return_value=None)
    return db


def identity_find_from_lookup(collection):
    original_find = getattr(collection, "find", None)
    if getattr(original_find, "_patient_identity_cursor", False) is True:
        return

    class Cursor:
        def __init__(self, query, projection, options):
            self.query, self.projection, self.options = query, projection, options

        async def to_list(self, length=None):
            rows = []
            for candidate in self.query['_id']['$in']:
                row = await collection.find_one({'_id': candidate})
                if not isinstance(row, dict) or type(row.get('_id')) is not type(candidate) or row['_id'] != candidate:
                    continue
                if any(type(old['_id']) is type(row['_id']) and old['_id'] == row['_id'] for old in rows):
                    continue
                projected = row
                if self.projection:
                    projected = {key: value for key, value in projected.items() if key == '_id' or self.projection.get(key)}
                rows.append(projected)
            return rows if length is None else rows[:length]

    def find(query, projection=None, **options):
        if isinstance(query.get('_id'), dict) and '$in' in query['_id'] and len(query) == 1:
            return Cursor(query, projection, options)
        return original_find(query, projection, **options)
    find._patient_identity_cursor = True
    collection.find = find
