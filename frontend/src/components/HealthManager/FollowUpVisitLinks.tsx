import React from 'react';
import { Box, Button, Stack, Typography } from '@mui/material';
import type { FollowUpRecord } from '../../types/followup';

export default function FollowUpVisitLinks({ record, onOpen }: { record: FollowUpRecord; onOpen?: (id: string) => void }) {
  const next = record.next_visit_id || record.next_follow_up_id;
  return <Stack spacing={0.5}>
    <Typography variant="subtitle2">访视关联</Typography>
    <Typography variant="body2">当前节点：{record.id}</Typography>
    {([['前次访视', record.previous_visit_id], ['后继访视', next]] as const).map(([label, id]) => <Box key={label}>
      <Typography component="span" variant="body2">{label}：{id || '无'}</Typography>
      {id && onOpen && <Button size="small" onClick={() => onOpen(id)}>查看{label}</Button>}
    </Box>)}
    {next && <Typography variant="body2" color="text.secondary">已有后继节点，不能重复发起复评。</Typography>}
  </Stack>;
}
