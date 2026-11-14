// 医护患者列表分页预适配（T59）的共享纯逻辑。
//
// 后端契约：GET /doctors/patients 的 skip/limit 为可选参数，缺省（不传）
// 保持一次性全量请求不变；显式分页时两域（legacy/canonical）执行同一约束
// （skip≥0、1≤limit≤200，越界 503 INVALID_PATIENT_PAGINATION）。
// canonical 域的缺省一次性返回受 list_assigned 仓库级缺省 limit=100 约束，
// 因此一次性拉取可能被截断——前端以 ONE_SHOT_CAP 作为「提供加载更多」的
// 触发阈值：legacy 域列表本就是全量，此时点击加载更多只会确认已全部加载；
// canonical 域则据此补齐剩余分页。
export const PATIENT_LIST_PAGE_SIZE = 50;
export const PATIENT_LIST_ONE_SHOT_CAP = 100;

type IdentifiedItem = { id: string };

// 归并一次性全量与「加载更多」批次：按 id 去重、保持加载顺序。
// 非法元素（缺失字符串 id）不进入结果，与患者选择器的名单校验同口径。
export function mergePatientBatches<T extends IdentifiedItem>(
  base: T[] | null | undefined,
  extra: T[] | null | undefined,
): T[] {
  const merged: T[] = [];
  const known = new Set<string>();
  for (const item of [...(base ?? []), ...(extra ?? [])]) {
    if (!item || typeof item.id !== 'string' || !item.id || known.has(item.id)) continue;
    known.add(item.id);
    merged.push(item);
  }
  return merged;
}

// 追加批次是否意味着已全部加载：后端返回不足一页（含空页）即无后续页。
export function patientBatchComplete(batchLength: number,
                                     pageSize: number = PATIENT_LIST_PAGE_SIZE): boolean {
  return batchLength < pageSize;
}

// 是否应提供「加载更多」：一次性加载已达上限阈值且尚未确认加载完。
export function patientLoadMoreAvailable(totalLoaded: number,
                                         allLoaded: boolean,
                                         oneShotCap: number = PATIENT_LIST_ONE_SHOT_CAP): boolean {
  return !allLoaded && totalLoaded >= oneShotCap;
}
