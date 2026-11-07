/**
 * 知情同意文档查看/签署（禁用占位）。
 * 原 /consent/documents/{id}、/consent/signatures、/consent/documents/{id}/pdf
 * 均为后端未注册的死链端点，能力待建设。
 */
import React from 'react';
import ConsentUnavailableNotice from './ConsentNotice';

const ConsentDocumentView: React.FC = () => (
  <ConsentUnavailableNotice
    title="知情同意文档详情"
    description="知情同意文档查看与签署功能暂未开放：后端尚未提供 /api/consent 文档、签名与 PDF 下载端点。"
  />
);

export default ConsentDocumentView;
