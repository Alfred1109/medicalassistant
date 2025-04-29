import React from 'react';
import FeatureUnderDevelopment from './components/common/FeatureUnderDevelopment';

interface DevelopmentPageProps {
  pageName: string;
  description?: string;
  returnPath?: string;
}

const SimpleDevelopmentApp: React.FC<DevelopmentPageProps> = ({
  pageName,
  description = '该页面正在开发中，请稍后再访问。',
  returnPath = '/'
}) => {
  return (
    <FeatureUnderDevelopment
      featureName={pageName}
      description={description}
      returnPath={returnPath}
      returnButtonText="返回首页"
    />
  );
};

export default SimpleDevelopmentApp; 