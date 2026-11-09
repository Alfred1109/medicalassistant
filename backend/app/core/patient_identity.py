"""Read-only legacy identity grouping; authorization remains with each domain.

ObjectId and its canonical string share an identity key. Multiple documents for
that key are deliberately returned together, never silently resolved. This
helper neither decides roles/permissions nor performs concurrency-fence writes.
"""
from bson import ObjectId


def identity_key(identifier):
    value = str(identifier)
    return str(ObjectId(value)) if ObjectId.is_valid(value) else value


def identity_candidates(identifiers):
    keys = []
    for identifier in identifiers:
        value = str(identifier)
        keys.append(value)
        if ObjectId.is_valid(value):
            keys.extend([str(ObjectId(value)), ObjectId(value)])
    return list(dict.fromkeys(keys))


def group_identity_documents(documents):
    groups = {}
    for document in documents:
        groups.setdefault(identity_key(document["_id"]), []).append(document)
    return groups


async def load_identity_groups(db, identifiers, *, projection=None, session=None):
    candidates = identity_candidates(identifiers)
    if not candidates:
        return {}
    if projection is not None:
        projection = {**projection, "_id": 1}
    documents = await db.users.find({"_id": {"$in": candidates}}, projection,
                                   session=session).to_list(length=None)
    return group_identity_documents(documents)
