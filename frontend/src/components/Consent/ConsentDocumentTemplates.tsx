// ... existing code ...

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
                  setCurrentTemplate({
                    ...currentTemplate,
                    content: e.target.value
                  });
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
                  setCurrentTemplate({
                    ...currentTemplate,
                    specialClauses: e.target.value
                  });
                }
              }}
              disabled={viewMode}
              placeholder="在此输入特殊条款或免责声明..."
              variant="outlined"
            />
          </Box>

// ... existing code ...