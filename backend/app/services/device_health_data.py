"""Map accepted real device readings into the health-data fact schema.

Raw payloads remain in device_data. No historical backfill, value-based dedup,
unit conversion or blood-pressure pairing is performed here.
"""
from copy import deepcopy

from app.models.health_record import HealthData
from app.core.fences import PatientFenceStore, legacy_document_fence
from app.core.patient_access import PatientAccessError, patient_domain_context


VITAL_TYPES = {
    "heart_rate": "heart_rate", "pulse": "heart_rate",
    "blood_glucose": "blood_glucose", "body_temperature": "body_temperature",
    "oxygen_saturation": "oxygen_saturation", "spo2": "oxygen_saturation",
    "respiration_rate": "respiratory_rate", "respiratory_rate": "respiratory_rate",
    "weight": "weight",
    # Separate components retain their own identity and measurement time.
    "blood_pressure_systolic": "blood_pressure_systolic",
    "blood_pressure_diastolic": "blood_pressure_diastolic",
    "systolic_pressure": "blood_pressure_systolic",
    "diastolic_pressure": "blood_pressure_diastolic",
}


async def fence_device_patient(db, patient_id, *, session):
    """Resolve the current patient domain; never infer a patient from an account ID."""
    context = await patient_domain_context(db, session=session)
    patient = await context.load_patient_doc(patient_id)
    if patient.get("is_active", True) is not True:
        raise PatientAccessError("患者不存在或不可用", error_code="PATIENT_NOT_FOUND", status_code=404)
    # domain-dispatch: 迁移完成后可删
    if context.is_canonical:
        await PatientFenceStore(db).bump(patient["patient_id"], "device", session=session,
                                         extra_query={"status": "active"})
    else:
        await legacy_document_fence(db.users, patient, "_device_access_fence", session=session,
            extra_query={"role": "patient", "is_active": patient.get("is_active")},
            error_code="DEVICE_PATIENT_FENCE_INVALID", error_message="设备所属患者并发状态无效",
            mismatch_code="DEVICE_PATIENT_CHANGED", mismatch_message="设备所属患者状态已变化")


def device_health_document(reading, patient_id):
    """Preserve accepted values, units, quality flags and immutable provenance."""
    metadata = reading.get("metadata") or {}
    if metadata.get("source") == "automated_simulated_replay" or metadata.get("simulated") is True:
        # Current clinical readers do not filter simulated values universally.
        return None
    data_type = reading["data_type"]
    document = HealthData(
        _id=str(reading["_id"]), patient_id=str(patient_id),
        data_type="vital_sign" if data_type in VITAL_TYPES else "device_measurement",
        data={"type": VITAL_TYPES.get(data_type, data_type),
              "value": deepcopy(reading["value"]), "unit": reading.get("unit")},
        source="device", device_id=reading["device_id"],
        recorded_by=metadata.get("recorded_by"), recorded_at=reading["timestamp"],
        created_at=reading["created_at"], updated_at=reading["created_at"],
        metadata={
            "device_data_id": str(reading["_id"]), "device_id": reading["device_id"],
            "device_data_type": data_type, "measurement_source": metadata.get("source"),
            "quality_flags": deepcopy(reading.get("quality_flags") or []),
            **{key: deepcopy(metadata[key]) for key in ("adapter_id", "session_id") if key in metadata},
        },
    )
    return document.to_mongo()


async def insert_device_health_data(db, reading, patient_id, *, session):
    document = device_health_document(reading, patient_id)
    if document is not None:
        await db.health_data.insert_one(document, session=session)
