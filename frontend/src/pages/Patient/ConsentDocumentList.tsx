/**
 * 知情同意文档列表（禁用占位）。
 * 原 /consent/documents 数据源为后端未注册的死链端点，能力待建设。
 */
import React from 'react';
import ConsentUnavailableNotice from './ConsentNotice';

const ConsentDocumentList: React.FC = () => (
  <ConsentUnavailableNotice
    title="知情同意文档"
    description="知情同意文档列表功能暂未开放：后端尚未提供 /api/consent/documents 端点。"
  />
);

export default ConsentDocumentList;
