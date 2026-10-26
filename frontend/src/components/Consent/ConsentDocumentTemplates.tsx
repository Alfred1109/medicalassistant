import React, { useState } from 'react';
import { Box, TextField } from '@mui/material';

// 知情同意书模板的正文内容
export interface ConsentTemplateContent {
  content: string;
  specialClauses?: string;
}

interface ConsentDocumentTemplatesProps {
  initialContent?: string;
  initialSpecialClauses?: string;
  readOnly?: boolean;
  onChange?: (template: ConsentTemplateContent) => void;
}

const ConsentDocumentTemplates: React.FC<ConsentDocumentTemplatesProps> = ({
  initialContent = '',
  initialSpecialClauses = '',
  readOnly = false,
  onChange,
}) => {
  const [currentTemplate, setCurrentTemplate] = useState<ConsentTemplateContent>({
    content: initialContent,
    specialClauses: initialSpecialClauses,
  });
  const [viewMode] = useState(readOnly);

  const updateTemplate = (patch: Partial<ConsentTemplateContent>) => {
    setCurrentTemplate((prev) => {
      const next = { ...prev, ...patch };
      onChange?.(next);
      return next;
    });
  };

  return (
    <>
      {/* 内容编辑器区域 */}
      <Box sx={{ p: 2 }}>
        <TextField
          fullWidth
          multiline
          rows={15}
          label="模板内容"
          value={currentTemplate?.content || ''}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
            if (currentTemplate) {
              updateTemplate({ content: e.target.value });
            }
          }}
          disabled={viewMode}
          placeholder="在此输入知情同意书的详细内容..."
          variant="outlined"
        />
      </Box>

      {/* 特殊条款区域 */}
      <Box sx={{ p: 2 }}>
        <TextField
          fullWidth
          multiline
          rows={5}
          label="特殊条款（可选）"
          value={currentTemplate?.specialClauses || ''}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
            if (currentTemplate) {
              updateTemplate({ specialClauses: e.target.value });
            }
          }}
          disabled={viewMode}
          placeholder="在此输入特殊条款或免责声明..."
          variant="outlined"
        />
      </Box>
    </>
  );
};

export default ConsentDocumentTemplates;
