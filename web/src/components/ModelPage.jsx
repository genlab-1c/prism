/* PRISM web — обёртка экрана модели для отдельной страницы /m/[id].
   В SPA навигация ведётся состоянием (App.jsx); здесь страница самостоятельная,
   поэтому «назад» — настоящий переход на главную (для шаринг-ссылок и OG). */
import React from 'react';
import { ModelDetailScreen } from './screens/ModelDetail.jsx';

const BASE = import.meta.env.BASE_URL;

export default function ModelPage({ modelId, data = {} }) {
  const { models = [], meta = {} } = data;
  const navigate = () => { if (typeof window !== 'undefined') window.location.href = BASE; };
  return <ModelDetailScreen modelId={modelId} models={models} meta={meta} navigate={navigate} />;
}
