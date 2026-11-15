import { Alert, Box, Typography } from '@mui/material';
import { formatAppDate } from '../../utils/dateTime';
import { healthDataValueText, type HealthObservation } from '../../utils/healthDataFacts';

export default function HealthDataQualityNotice({ observations, label = type => type }: {
  observations: HealthObservation[]; label?: (type: string) => string;
}) {
  const flagged = observations.filter(point => point.qualityFlags.length > 0);
  if (!flagged.length) return null;
  return <Alert severity="warning" sx={{ my: 2 }}>
    <Typography variant="body2">所加载记录中有 {flagged.length} 条读数带质量标记，原值保留供核查，未纳入趋势；标记不代表临床诊断。</Typography>
    {flagged.map((point, index) => <Box key={`${point.id}-${point.type}-${index}`} sx={{ mt: 1 }}>
      {label(point.type)}：{healthDataValueText(point.rawValue)} {point.unit}；
      {formatAppDate(point.timestamp, 'localeZh24', { assumeUtc: true, empty: '时间未提供', invalid: point.timestamp })}；
      质量标记：{point.qualityFlags.join('、')}
    </Box>)}
  </Alert>;
}
