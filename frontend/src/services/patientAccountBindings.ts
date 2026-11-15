import api from './httpClient';

// T77 显式账号绑定管理：消费后端 T64 端点
// （backend/app/api/routers/patient_account_binding_router.py，挂载于 /api）。
// 能力边界（探查结论）：后端仅提供 admin-only 创建与停用两个写端点，
// 没有列表/查询端点——「查询链接状态」只能在操作后由响应回显。
// 互斥语义：患者或账号已有任意 origin 的链接（含已停用）一律 409，
// 不做隐式替换；停用为终态，重新绑定需人工核实对账。

// 绑定状态响应（对齐后端 AccountBindingResponse）
export interface AccountBinding {
  patient_id: string;
  /** 登录账号 ID（24 位 ObjectId） */
  account_id: string;
  /** verified / disabled */
  status: string;
  /** 显式绑定 origin（explicit_binding） */
  source: string;
  reviewer?: string | null;
  evidence_reference?: string | null;
  bound_at?: string | null;
  disabled_at?: string | null;
}

export interface AccountBindingCreatePayload {
  patient_id: string;
  account_id: string;
  /** 人工核实人（审计必填） */
  reviewer: string;
  /** 凭证引用（审计必填，如对账材料编号） */
  evidence_reference: string;
}

export interface AccountBindingDisablePayload {
  reviewer: string;
  evidence_reference: string;
}

// 仓储 PatientDomainError → HTTP 状态映射（patient_account_binding_router._BINDING_ERROR_STATUS）
const DOMAIN_ERROR_COPY: Record<string, string> = {
  PATIENT_REVIEW_REQUIRED: '患者档案尚未完成人工核实，请先在患者域完成审核。',
  INVALID_PATIENT_REVIEW_REFERENCE: '患者核实引用无效，请核对后重试。',
  INVALID_PATIENT_ACCOUNT: '账号不存在或不是可绑定的登录账号。',
  PATIENT_NOT_FOUND: '患者不存在。',
  PATIENT_ACCOUNT_LINK_NOT_FOUND: '该患者没有可停用的账号链接。',
  PATIENT_ACCOUNT_LINK_CONFLICT: '该患者或账号已存在绑定链接（含已停用）；系统不做隐式替换，请走人工核实对账流程。',
  PATIENT_DOMAIN_NOT_MIGRATED: '患者域尚未完成迁移，绑定功能暂不可用。',
  PATIENT_DOMAIN_STATE_UNAVAILABLE: '患者域状态不可用，请稍后重试。',
  PATIENT_DOMAIN_INDEX_MISSING: '患者域索引缺失，请联系管理员处理。',
  PATIENT_DOMAIN_INDEX_CHECK_FAILED: '患者域索引校验失败，请稍后重试。',
};

/** 将后端绑定失败映射为面向管理员的中文文案；未知错误原样透传 */
export const accountBindingErrorCopy = (failure: unknown): string => {
  const detail = (failure as { response?: { data?: { detail?: { error?: string; message?: string } | string } } })
    ?.response?.data?.detail;
  if (detail && typeof detail === 'object') {
    const copy = detail.error ? DOMAIN_ERROR_COPY[detail.error] : undefined;
    return copy || detail.message || detail.error || '操作失败，请稍后重试。';
  }
  if (typeof detail === 'string' && detail) return detail;
  return (failure as Error)?.message || '操作失败，请稍后重试。';
};

export const patientAccountBindingService = {
  /** 为临床患者显式绑定登录账号（人工核实后；审计必填；409=已存在链接） */
  createBinding: async (payload: AccountBindingCreatePayload): Promise<AccountBinding> => {
    const { data } = await api.post('/patients/account-bindings', payload);
    return data;
  },

  /** 停用患者的显式账号链接（verified→disabled 状态机；不删除、不复活） */
  disableBinding: async (patientId: string, payload: AccountBindingDisablePayload): Promise<AccountBinding> => {
    const { data } = await api.post(
      `/patients/account-bindings/${encodeURIComponent(patientId)}/disable`,
      payload,
    );
    return data;
  },
};
