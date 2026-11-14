// 患者域错误语义 → 用户提示文案。
// 后端全局异常处理器（backend/app/main.py AppBaseException handler）统一返回
// { error: <error_code>, message, details, request_id }；本模块只做展示层映射，
// 不改变请求与状态码语义。
export const PATIENT_DOMAIN_ERROR_COPY: Record<string, string> = {
  // 存量数据中同一患者标识对应多个实体，读取 fail-closed（503）
  PATIENT_IDENTITY_AMBIGUOUS: '患者档案标识存在歧义，请联系管理员核查历史数据。',
  QUALITY_PATIENT_IDENTITY_AMBIGUOUS: '患者档案标识存在歧义，请联系管理员核查历史数据。',
  // 质控域：患者范围未核实 / 身份无法唯一确定（503）
  QUALITY_PATIENT_SCOPE_UNVERIFIED: '患者身份存在歧义，请先完成患者范围核实后再查询。',
  // 随访提醒域：患者账号域不受支持（503）
  REMINDER_PATIENT_DOMAIN_UNSUPPORTED: '该患者档案类型暂不支持随访提醒，请确认患者账号域。',
  // 康复域：患者档案尚未接入康复账号解析（503）
  REHAB_PATIENT_DOMAIN_UNSUPPORTED: '当前患者档案尚未接入康复账号，暂不支持康复计划相关操作。',
  // 患者域开关状态不可用，访问被拒绝（503）
  PATIENT_DOMAIN_STATE_UNAVAILABLE: '患者域状态暂时不可用，请稍后重试；若持续出现请联系管理员。',
};

type ApiErrorShape = { response?: { status?: number; data?: { error?: unknown } } };

// 提取患者域错误码；这些错误码由后端统一以 503 抛出（读取 fail-closed 语义），
// 其余状态码（409/403 等）有各自的展示文案，不在本映射范围内。
export function patientDomainErrorCode(error: unknown): string | null {
  const response = (error as ApiErrorShape)?.response;
  if (response?.status !== 503) return null;
  const code = response?.data?.error;
  return typeof code === 'string' && PATIENT_DOMAIN_ERROR_COPY[code] ? code : null;
}

// 患者域错误对应的统一提示文案；非患者域错误返回 null（由调用方走原有提示路径）。
export function patientDomainErrorCopy(error: unknown): string | null {
  const code = patientDomainErrorCode(error);
  return code ? PATIENT_DOMAIN_ERROR_COPY[code] : null;
}

// 在 axios 响应拦截器里就地改写 error.message，保持错误对象身份不变
// （httpClient 现有测试断言 error === failure）。非患者域错误原样返回。
// 用 message 字段的存在性而不是 instanceof 判断，避免跨执行环境（如 vm 沙箱）失效。
export function applyPatientDomainErrorCopy<T>(error: T): T {
  const copy = patientDomainErrorCopy(error);
  const target = error as { message?: unknown } | null;
  if (copy && target && typeof target.message === 'string') target.message = copy;
  return error;
}
