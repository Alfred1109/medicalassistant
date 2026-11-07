/**
 * 知情同意文档模板列表（禁用占位）。
 * 原 /consent/templates、/consent/documents/generate 均为后端未注册的死链端点，能力待建设。
 */
import React from 'react';
import ConsentUnavailableNotice from './ConsentNotice';

const ConsentTemplateList: React.FC = () => (
  <ConsentUnavailableNotice
    title="知情同意文档模板"
    description="知情同意模板功能暂未开放：后端尚未提供 /api/consent/templates 端点。"
  />
);

export default ConsentTemplateList;
