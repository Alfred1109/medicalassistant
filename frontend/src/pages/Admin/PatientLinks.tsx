import React, { useCallback, useState } from 'react';
import { Alert, Box, MenuItem, Paper, Tab, Tabs, TextField, Typography } from '@mui/material';
import { formCatalog } from '../../services/formCatalog';
import { useFormCatalog } from '../../hooks/useFormCatalog';
import type { CatalogCenter, CatalogProject, CatalogSubject } from '../../types/formCatalog';
import CatalogPageState from '../../components/Admin/CatalogPageState';
import PatientLinkPanel from '../../components/Admin/PatientLinkPanel';
import FormBindingPanel from '../../components/Admin/FormBindingPanel';

export default function PatientLinks() {
  const [projectId, setProjectId] = useState(0);
  const [centerId, setCenterId] = useState(0);
  const [subjectId, setSubjectId] = useState(0);
  const [tab, setTab] = useState(0);
  const projectLoader = useCallback((cursor: string | undefined, signal: AbortSignal) => formCatalog.projects({ cursor }, signal), []);
  const projects = useFormCatalog<CatalogProject>('projects', projectLoader);
  const centerLoader = useCallback((cursor: string | undefined, signal: AbortSignal) => formCatalog.centers(projectId, { cursor }, signal), [projectId]);
  const centers = useFormCatalog<CatalogCenter>(`centers:${projectId}`, projectId ? centerLoader : null);
  const subjectLoader = useCallback((cursor: string | undefined, signal: AbortSignal) => formCatalog.subjects(projectId, centerId, { cursor }, signal), [projectId, centerId]);
  const subjects = useFormCatalog<CatalogSubject>(`subjects:${projectId}:${centerId}`, projectId && centerId ? subjectLoader : null);
  const project = projects.items.find(item => item.project_id === projectId) || null;
  const center = centers.items.find(item => item.center_id === centerId && item.project_id === projectId) || null;
  const subject = subjects.items.find(item => item.subject_id === subjectId && item.project_id === projectId && item.center_id === centerId) || null;

  return <Box>
    <Typography variant="h5" component="h1" gutterBottom>患者与问卷来源</Typography>
    <Typography color="text.secondary" sx={{ mb: 2 }}>从问卷平台获授权的项目中核实患者对应关系，并选择康复业务使用的正式问卷。</Typography>
    <Alert severity="info" sx={{ mb: 2 }}>患者关联和问卷选择需要管理员核实。此处不创建患者账号，也不发起填报。</Alert>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mb: 3 }}>
      <TextField select fullWidth label="来源项目" value={projectId || ''} onChange={event => { setProjectId(Number(event.target.value)); setCenterId(0); setSubjectId(0); }} disabled={projects.loading}>
        <MenuItem value="" disabled>请选择项目</MenuItem>
        {projects.items.map(item => <MenuItem key={item.project_id} value={item.project_id}>{item.name} · 项目 #{item.project_id}</MenuItem>)}
      </TextField>
      <CatalogPageState {...projects} />
      {!projects.loading && !projects.error && projects.items.length === 0 && <Typography variant="body2" sx={{ mt: 1 }}>当前没有可访问的项目。请先在问卷平台配置明确的项目授权。</Typography>}
      {project && <Typography variant="caption" component="p" sx={{ mt: 1 }}>来源：{project.source.system} · {project.source.environment === 'production' ? '正式环境' : project.source.environment}</Typography>}
    </Paper>
    <Tabs value={tab} onChange={(_, next: number) => setTab(next)} sx={{ mb: 2 }} variant="scrollable">
      <Tab label="患者关联" /><Tab label="问卷用途" />
    </Tabs>
    {tab === 0 && <>
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mb: 3 }}>
        <Typography variant="h6" gutterBottom>选择来源患者</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
          <Box>
            <TextField select fullWidth label="所属中心" value={centerId || ''} disabled={!project || centers.loading} onChange={event => { setCenterId(Number(event.target.value)); setSubjectId(0); }}>
              <MenuItem value="" disabled>请选择中心</MenuItem>
              {centers.items.filter(item => item.project_id === projectId).map(item => <MenuItem key={item.center_id} value={item.center_id}>{item.name || item.center_code} · 中心 #{item.center_id}</MenuItem>)}
            </TextField><CatalogPageState {...centers} />
          </Box>
          <Box>
            <TextField select fullWidth label="项目受试者" value={subjectId || ''} disabled={!center || subjects.loading} onChange={event => setSubjectId(Number(event.target.value))}>
              <MenuItem value="" disabled>请选择受试者代码</MenuItem>
              {subjects.items.filter(item => item.project_id === projectId && item.center_id === centerId).map(item => <MenuItem key={item.subject_id} value={item.subject_id}>{item.code || '无代码'} · 受试者 #{item.subject_id} · {item.status}</MenuItem>)}
            </TextField><CatalogPageState {...subjects} />
          </Box>
        </Box>
        {project && !centers.loading && !centers.error && centers.items.length === 0 && <Typography variant="body2" sx={{ mt: 2 }}>该项目没有获授权的中心。</Typography>}
        {center && !subjects.loading && !subjects.error && subjects.items.length === 0 && <Typography variant="body2" sx={{ mt: 2 }}>该中心没有获授权的受试者。</Typography>}
      </Paper>
      <PatientLinkPanel key={`${projectId}:${centerId}:${subjectId}`} project={project} center={center} subject={subject} />
    </>}
    {tab === 1 && <FormBindingPanel key={projectId} project={project} />}
  </Box>;
}
