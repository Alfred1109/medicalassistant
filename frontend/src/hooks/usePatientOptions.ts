import { useCallback } from 'react';
import api from '../services/httpClient';
import { useAsyncResource } from './useAsyncResource';

export interface PatientOption { id: string; name: string; diagnosis?: string; age?: number; gender?: string }

export function usePatientOptions(role?: string, actorId?: string, includeAdmin = false) {
  const admin = includeAdmin && role === 'admin';
  const enabled = Boolean(actorId) && (role === 'doctor' || role === 'health_manager' || admin);
  const load = useCallback(async (signal: AbortSignal): Promise<PatientOption[]> => {
    const url = admin ? '/admin/patients' : role === 'health_manager' ? '/health-managers/patients' : '/doctors/patients';
    const { data } = await api.get<Array<Partial<PatientOption> & { _id?: string }>>(url,
      { signal, ...(admin ? { params: { limit: 1000 } } : {}) });
    if (!Array.isArray(data)) throw new Error('患者目录响应格式无效');
    const seen = new Set<string>();
    return data.flatMap(patient => {
      const id = String(patient?.id || patient?._id || '');
      if (!id || seen.has(id)) return [];
      seen.add(id);
      return [{ id, name: String(patient.name || '未命名患者'),
        ...(typeof patient.diagnosis === 'string' ? { diagnosis: patient.diagnosis } : {}),
        ...(typeof patient.age === 'number' ? { age: patient.age } : {}),
        ...(typeof patient.gender === 'string' ? { gender: patient.gender } : {}),
      }];
    });
  }, [role, actorId, admin]);
  const resource = useAsyncResource(load, enabled);
  return { ...resource, patients: resource.data ?? [] };
}
