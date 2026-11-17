function heartRateCallbackFailure(event) {
  const content = event && event.content || {};
  if (content.deviceBusy === true) return 'device_busy';
  if (content.notWear === true) return 'not_worn';
  return null;
}

function normalizeHeartRateCallback(event, hardwareId, receivedAt) {
  if (!event || Number(event.type) !== 51) return null;
  if (heartRateCallbackFailure(event)) return null;
  const content = event.content || {};
  const value = Number(content.heartRate);
  if (!Number.isFinite(value) || value < 30 || value > 250) return null;
  if (!hardwareId || typeof hardwareId !== 'string') return null;
  const measuredAt = new Date(receivedAt);
  if (Number.isNaN(measuredAt.getTime())) return null;
  const offsetMinutes = -measuredAt.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const offsetHours = String(Math.floor(Math.abs(offsetMinutes) / 60)).padStart(2, '0');
  const offsetRemainder = String(Math.abs(offsetMinutes) % 60).padStart(2, '0');
  const localTimestamp = `${measuredAt.getFullYear()}-${String(measuredAt.getMonth() + 1).padStart(2, '0')}-${String(measuredAt.getDate()).padStart(2, '0')}T${String(measuredAt.getHours()).padStart(2, '0')}:${String(measuredAt.getMinutes()).padStart(2, '0')}:${String(measuredAt.getSeconds()).padStart(2, '0')}.${String(measuredAt.getMilliseconds()).padStart(3, '0')}${sign}${offsetHours}:${offsetRemainder}`;
  return {
    data_type: 'heart_rate',
    value: String(value),
    unit: 'bpm',
    measured_at: localTimestamp,
    sdk_type: 51,
    record_key: `${hardwareId}:heart_rate:${measuredAt.getTime()}`,
    raw_payload: { heartRate: value, heartState: content.heartState, watchState: content.watchState,
      capture_time_source: 'phone_callback', phone_timezone_offset_minutes: offsetMinutes },
  };
}

module.exports = { heartRateCallbackFailure, normalizeHeartRateCallback };
