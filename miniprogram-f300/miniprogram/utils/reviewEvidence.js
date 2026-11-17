const { sha256 } = require('./miniAuth');

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
}

function patientSelfSnapshotDigest(evidence) {
  const fields = ['fill_mode', 'session_uuid', 'response_id', 'remote_status', 'submitted_at',
    'updated_at', 'questionnaire_version_ref', 'visit_code', 'answers'];
  const snapshot = {};
  fields.forEach(key => { snapshot[key] = evidence[key] === undefined ? null : evidence[key]; });
  const encoded = unescape(encodeURIComponent(stableJson(snapshot)));
  const bytes = new Uint8Array(encoded.length);
  for (let i = 0; i < encoded.length; i += 1) bytes[i] = encoded.charCodeAt(i);
  return Array.from(sha256(bytes), value => value.toString(16).padStart(2, '0')).join('');
}

module.exports = { patientSelfSnapshotDigest };
