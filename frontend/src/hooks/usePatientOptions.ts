import { useCallback } from 'react';
import api from '../services/httpClient';
import { useAsyncResource } from './useAsyncResource';

export interface PatientOption { id: string; name: string; diagnosis?: string; age?: number; gender?: string }

export function usePatientOptions(role?: string, actorId?: string) {
  const enabled = Boolean(actorId) && (role === 'doctor' || role === 'health_manager');
  const load = useCallback(async (signal: AbortSignal): Promise<PatientOption[]> => {
    if (!actorId || (role !== 'doctor' && role !== 'health_manager')) return [];
    const url = role === 'health_manager' ? '/health-managers/patients' : '/doctors/patients';
    const { data } = await api.get<Array<Partial<PatientOption> & { _id?: string }>>(url, { signal });
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
  }, [role, actorId]);
  const resource = useAsyncResource(load, enabled);
  return { ...resource, patients: resource.data ?? [] };
}
