import type { PatientSelfLaunch, PatientSelfTask } from '../services/formIntegrationService';

export const patientQuestionnairePath = '/app/patient/questionnaires';
export const validQuestionnaireTaskId = (id: string) => /^[a-f0-9]{24}$/i.test(id);

export const patientQuestionnaireStatus: Record<string, string> = {
  assigned: '待填写', active: '填写中', submitted: '已提交 · 待医护核实', confirmed: '已核实',
  revoking: '正在取消', revoked: '已取消', cancelled: '已取消', revoke_failed: '取消处理中', expired: '已过期',
};

export function patientQuestionnaireTitle(task: PatientSelfTask): string {
  return task.questionnaireTitle?.trim() || task.visitName?.trim() || `问卷 ${task.remoteRefs.questionnaire_id}`;
}

export function patientSelfBridgeUrl(result: PatientSelfLaunch, taskId: string, origin: string, apiBase: string): URL {
  const api = new URL(apiBase, origin);
  const target = new URL(result.webviewUrl);
  const prefix = `${api.pathname.replace(/\/$/, '')}/integrations/forms/patient-self/launch-bridge/`;
  const ticket = target.pathname.slice(prefix.length);
  if (result.taskId !== taskId || result.allowedOrigin !== origin || api.origin !== origin ||
      target.protocol !== 'https:' || target.origin !== origin || target.username || target.password ||
      !target.pathname.startsWith(prefix) || !/^[A-Za-z0-9_-]{32,128}$/.test(ticket) || target.search || target.hash) {
    throw new Error('问卷入口与当前任务或站点不匹配，请重新打开。');
  }
  return target;
}
