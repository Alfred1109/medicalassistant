/** Preserve scalar and composite readings; quality is displayed separately. */
export function timelineMeasurement(values?: Record<string, unknown>): string | null {
  if (!values) return null;
  const value = values.result_value ?? values.value;
  if (value === null || value === undefined) return null;
  const reading = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return `${String(values.test_name ?? values.type ?? '读数')}：${reading}${values.unit ? ` ${String(values.unit)}` : ''}`;
}
