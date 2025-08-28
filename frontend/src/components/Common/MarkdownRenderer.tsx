import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { Box, Paper, Typography } from '@mui/material';
import { styled } from '@mui/material/styles';

// 样式化的容器
const MarkdownContainer = styled(Box)(({ theme }) => ({
  '& h1, & h2, & h3, & h4, & h5, & h6': {
    color: theme.palette.text.primary,
    fontWeight: 600,
    marginTop: theme.spacing(2),
    marginBottom: theme.spacing(1),
  },
  '& h1': {
    fontSize: '2rem',
    borderBottom: `2px solid ${theme.palette.divider}`,
    paddingBottom: theme.spacing(1),
  },
  '& h2': {
    fontSize: '1.5rem',
    borderBottom: `1px solid ${theme.palette.divider}`,
    paddingBottom: theme.spacing(0.5),
  },
  '& h3': {
    fontSize: '1.25rem',
  },
  '& p': {
    marginBottom: theme.spacing(1),
    lineHeight: 1.6,
  },
  '& ul, & ol': {
    paddingLeft: theme.spacing(3),
    marginBottom: theme.spacing(1),
  },
  '& li': {
    marginBottom: theme.spacing(0.5),
  },
  '& blockquote': {
    borderLeft: `4px solid ${theme.palette.primary.main}`,
    paddingLeft: theme.spacing(2),
    marginLeft: 0,
    marginRight: 0,
    fontStyle: 'italic',
    backgroundColor: theme.palette.grey[50],
    padding: theme.spacing(1, 2),
  },
  '& code': {
    backgroundColor: theme.palette.grey[100],
    padding: '2px 4px',
    borderRadius: '4px',
    fontSize: '0.875rem',
    fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
  },
  '& pre': {
    backgroundColor: theme.palette.grey[900],
    color: theme.palette.common.white,
    padding: theme.spacing(2),
    borderRadius: theme.shape.borderRadius,
    overflow: 'auto',
    marginBottom: theme.spacing(1),
    '& code': {
      backgroundColor: 'transparent',
      padding: 0,
      color: 'inherit',
    },
  },
  '& table': {
    width: '100%',
    borderCollapse: 'collapse',
    marginBottom: theme.spacing(1),
    '& th, & td': {
      border: `1px solid ${theme.palette.divider}`,
      padding: theme.spacing(1),
      textAlign: 'left',
    },
    '& th': {
      backgroundColor: theme.palette.grey[100],
      fontWeight: 600,
    },
  },
  '& a': {
    color: theme.palette.primary.main,
    textDecoration: 'none',
    '&:hover': {
      textDecoration: 'underline',
    },
  },
  '& img': {
    maxWidth: '100%',
    height: 'auto',
    borderRadius: theme.shape.borderRadius,
  },
  '& hr': {
    border: 'none',
    borderTop: `1px solid ${theme.palette.divider}`,
    margin: theme.spacing(2, 0),
  },
}));

interface MarkdownRendererProps {
  content: string;
  variant?: 'default' | 'card';
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ 
  content, 
  variant = 'default' 
}) => {
  if (!content) {
    return (
      <Typography variant="body2" color="text.secondary">
        暂无内容
      </Typography>
    );
  }

  const markdownContent = (
    <MarkdownContainer>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // 自定义组件渲染
          p: ({ children }) => (
            <Typography variant="body1" component="p" gutterBottom>
              {children}
            </Typography>
          ),
          h1: ({ children }) => (
            <Typography variant="h4" component="h1" gutterBottom>
              {children}
            </Typography>
          ),
          h2: ({ children }) => (
            <Typography variant="h5" component="h2" gutterBottom>
              {children}
            </Typography>
          ),
          h3: ({ children }) => (
            <Typography variant="h6" component="h3" gutterBottom>
              {children}
            </Typography>
          ),
          h4: ({ children }) => (
            <Typography variant="subtitle1" component="h4" gutterBottom>
              {children}
            </Typography>
          ),
          h5: ({ children }) => (
            <Typography variant="subtitle2" component="h5" gutterBottom>
              {children}
            </Typography>
          ),
          h6: ({ children }) => (
            <Typography variant="subtitle2" component="h6" gutterBottom>
              {children}
            </Typography>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </MarkdownContainer>
  );

  if (variant === 'card') {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        {markdownContent}
      </Paper>
    );
  }

  return markdownContent;
};

export default MarkdownRenderer;
