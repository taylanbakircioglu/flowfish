import React from 'react';
import { Button, message, theme } from 'antd';
import { CopyOutlined } from '@ant-design/icons';

const { useToken } = theme;

interface CodeBlockProps {
  code: string;
  label: string;
  maxHeight?: number;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ code, label, maxHeight }) => {
  const { token } = useToken();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      message.success(`${label} copied`);
    } catch {
      message.error('Clipboard unavailable');
    }
  };

  if (!code) {
    return (
      <pre
        style={{
          background: token.colorBgLayout,
          color: token.colorTextSecondary,
          padding: 16,
          borderRadius: 8,
          fontSize: 12,
          margin: 0,
          border: `1px solid ${token.colorBorderSecondary}`,
          textAlign: 'center',
        }}
      >
        Configure search parameters in the previous step to generate this snippet.
      </pre>
    );
  }

  return (
    <div style={{ position: 'relative' }}>
      <Button
        size="small"
        icon={<CopyOutlined />}
        onClick={copy}
        style={{ position: 'absolute', top: 8, right: 8, zIndex: 1, opacity: 0.85 }}
      >
        Copy
      </Button>
      <pre
        style={{
          background: token.colorBgLayout,
          color: token.colorText,
          padding: 16,
          borderRadius: 8,
          overflow: 'auto',
          fontSize: 12,
          margin: 0,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          border: `1px solid ${token.colorBorderSecondary}`,
          maxHeight: maxHeight,
        }}
      >
        {code}
      </pre>
    </div>
  );
};

export default CodeBlock;
