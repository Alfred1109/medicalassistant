import React, { useEffect, useState } from 'react';
import {
  Alert, Box, Button, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { formCatalog, formCatalogError } from '../../services/formCatalog';
import type { CatalogProject, ImportedPerson, ImportedRole } from '../../types/formCatalog';

const ROLE_LABELS: Record<ImportedRole, string> = {
  unassigned: '未指定',
  patient: '患者',
  doctor: '医生',
  health_manager: '健康管理师',
};

export default function ProjectPeoplePanel({ project }: { project: CatalogProject | null }) {
  const [people, setPeople] = useState<ImportedPerson[]>([]);
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!project) {
      setPeople([]);
      return;
    }
    const controller = new AbortController();
    formCatalog.importedPeople(project.project_id, controller.signal)
      .then(response => setPeople(response.data.people))
      .catch(reason => {
        if (!controller.signal.aborted) setError(formCatalogError(reason, '暂时无法读取已导入的人员。'));
      });
    return () => controller.abort();
  }, [project]);

  const importPeople = async () => {
    if (!project) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await formCatalog.importPeople(project.project_id);
      setPeople(response.data.people);
      setNotice(`新导入 ${response.data.created} 人，已存在 ${response.data.existing} 人。受试者记为患者，其他成员尚未指定角色。`);
    } catch (reason) {
      setError(formCatalogError(reason, '导入项目人员失败。'));
    } finally {
      setBusy(false);
    }
  };

  const saveRole = async (person: ImportedPerson, role: ImportedRole) => {
    const reference = (evidence[person.id] || '').trim();
    if (!reference) {
      setError('切换角色前请填写核实依据。');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await formCatalog.assignImportedRole(person.id, role, reference);
      const refreshed = await formCatalog.importedPeople(project!.project_id);
      setPeople(refreshed.data.people);
      setNotice('角色已更新。原先负责的患者已清空；已绑定的登录需要重新确认后才能继续使用。');
    } catch (reason) {
      setError(formCatalogError(reason, '保存角色失败。'));
    } finally {
      setBusy(false);
    }
  };

  const saveCare = async (patient: ImportedPerson, practitionerId: string, assigned: boolean) => {
    const reference = (evidence[patient.id] || '').trim();
    if (!reference) {
      setError('指定负责人前请填写核实依据。');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await formCatalog.setImportedCare(patient.id, practitionerId, assigned, reference);
      setPeople(current => current.map(item => item.id === patient.id ? response.data : item));
      setNotice(assigned ? '已指定负责人。' : '已取消负责关系。');
    } catch (reason) {
      setError(formCatalogError(reason, '保存负责关系失败。'));
    } finally {
      setBusy(false);
    }
  };

  const clinicians = people.filter(person => person.role === 'doctor' || person.role === 'health_manager');

  if (!project) return <Alert severity="info">先选择一个已授权的来源项目。</Alert>;
  return <Box>
    <Typography color="text.secondary" sx={{ mb: 2 }}>
      受试者导入为患者。其他项目成员先不指定角色，之后可以改成医生、健康管理师或患者。同名人员不会自动合并。
    </Typography>
    <Button variant="contained" onClick={importPeople} disabled={busy}>导入本项目人员</Button>
    {notice && <Alert severity="success" sx={{ mt: 2 }}>{notice}</Alert>}
    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
    <TableContainer component={Paper} sx={{ mt: 2 }}><Table>
      <TableHead>
        <TableRow>
          <TableCell>本地编号</TableCell>
          <TableCell>姓名</TableCell>
          <TableCell>来源</TableCell>
          <TableCell>角色</TableCell>
          <TableCell>负责人</TableCell>
          <TableCell>核实依据</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {people.map(person => <TableRow key={person.id}>
          <TableCell>{person.id}</TableCell>
          <TableCell>{person.name}</TableCell>
          <TableCell>{person.source_kind === 'subject' ? `受试者 ${person.subject_code || ''}` : '项目成员'}</TableCell>
          <TableCell>
            <TextField select size="small" value={person.role} disabled={busy}
              onChange={event => saveRole(person, event.target.value as ImportedRole)}>
              {(Object.keys(ROLE_LABELS) as ImportedRole[]).map(role => <MenuItem key={role} value={role}>{ROLE_LABELS[role]}</MenuItem>)}
            </TextField>
          </TableCell>
          <TableCell>
            {person.role === 'patient' ? <TextField select size="small" value={[...person.practitioners, ...person.health_managers]} disabled={busy}
              SelectProps={{ multiple: true }}
              onChange={event => {
                const next = event.target.value as unknown as string[];
                const current = [...person.practitioners, ...person.health_managers];
                const added = next.find(id => !current.includes(id));
                const removed = current.find(id => !next.includes(id));
                if (added) saveCare(person, added, true);
                if (removed) saveCare(person, removed, false);
              }}>
              {clinicians.map(clinician => <MenuItem key={clinician.id} value={clinician.id}>{clinician.name} · {ROLE_LABELS[clinician.role]}</MenuItem>)}
            </TextField> : '—'}
          </TableCell>
          <TableCell>
            <TextField size="small" value={evidence[person.id] || ''} placeholder="变更时必填"
              onChange={event => setEvidence(current => ({ ...current, [person.id]: event.target.value }))} />
          </TableCell>
        </TableRow>)}
        {people.length === 0 && <TableRow><TableCell colSpan={6}>这个项目还没有导入人员。</TableCell></TableRow>}
      </TableBody>
    </Table></TableContainer>
  </Box>;
}
