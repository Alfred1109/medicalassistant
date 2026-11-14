"""Read adapter for the currently active users-backed patient domain.

This adapter makes the legacy storage boundary explicit. It never selects or
falls back from canonical storage; switching the patient domain remains a
separate migration of all business consumers.
"""
import re

from bson import ObjectId
from app.core.exceptions import AppBaseException
from app.core.patient_identity import identity_key, load_identity_groups


class LegacyPatientIdentityError(AppBaseException):
    def __init__(self):
        super().__init__("患者标识对应多个实体，请先核实", status_code=503,
                         error_code="PATIENT_IDENTITY_AMBIGUOUS")


def self_patient_id(account_id, role, requested_id=None):
    """Resolve the authenticated legacy same-document relation explicitly.

    Authentication owns account validity. Legacy patient accounts intrinsically
    share their document ID with the clinical entity; this function does not
    infer a canonical account link or grant a medical role self-patient access.
    """
    if role != "patient" or not isinstance(account_id, (str, ObjectId)) or not str(account_id):
        return None
    identifier = str(account_id)
    if requested_id is not None and (
            not isinstance(requested_id, (str, ObjectId)) or str(requested_id) != identifier):
        return None
    return identifier


class LegacyPatientRepository:
    def __init__(self, db):
        self.db = db
        self.collection = db.users

    async def get(self, patient_id, *, session=None):
        groups = await load_identity_groups(self.db, [patient_id], session=session)
        documents = groups.get(identity_key(patient_id), [])
        if len(documents) > 1:
            raise LegacyPatientIdentityError()
        return documents[0] if documents and documents[0].get("role") == "patient" else None

    async def assigned_ids(self, assignment_query):
        """Read an already constructed role-specific authorization query."""
        cursor = self.collection.find(assignment_query, {"_id": 1})
        identifiers = [str(document["_id"]) async for document in cursor]
        await self._unambiguous(identifiers)
        return identifiers

    async def _unambiguous(self, identifiers, *, session=None):
        groups = await load_identity_groups(self.db, identifiers, session=session)
        if any(len(documents) > 1 for documents in groups.values()):
            raise LegacyPatientIdentityError()
        return groups

    @staticmethod
    def _identifiers(patient_ids):
        return [value for item in patient_ids for value in
                ([item, ObjectId(item)] if ObjectId.is_valid(item) else [item])]

    async def matching_name_ids(self, name, *, patient_ids=None):
        query = {"role": "patient", "name": {"$regex": re.escape(name), "$options": "i"}}
        if patient_ids is not None:
            query["_id"] = {"$in": self._identifiers(patient_ids)}
        documents = await self.collection.find(query, {"_id": 1}).to_list(length=None)
        await self._unambiguous([document["_id"] for document in documents])
        return {str(document["_id"]) for document in documents}

    async def names(self, patient_ids):
        if not patient_ids:
            return {}
        groups = await self._unambiguous(patient_ids)
        documents = [document for entries in groups.values() for document in entries
                     if document.get("role") == "patient"]
        return {str(document["_id"]): document.get("name") for document in documents}
