/* PRISM web — островок главной: лидерборд + детальная модели (SPA-роутер
   внутри острова). Шапка/подвал теперь общие (layout), здесь только экраны.
   Тема живёт на <html data-theme> (CSS-переменные), JS-состояние ей не нужно. */
import React from 'react';
import { LeaderboardScreen } from './screens/Leaderboard.jsx';
import { ModelDetailScreen } from './screens/ModelDetail.jsx';

export default function App({ data = {} }) {
  const { models = [], meta = {} } = data;
  const [route, setRoute] = React.useState({ screen: 'leaderboard', modelId: null });

  const navigate = (screen, modelId = null) => {
    setRoute({ screen, modelId });
    if (typeof window !== 'undefined') window.scrollTo({ top: 0 });
  };

  return route.screen === 'model'
    ? <ModelDetailScreen modelId={route.modelId} models={models} navigate={navigate} />
    : <LeaderboardScreen navigate={navigate} models={models} meta={meta} />;
}
