/* PRISM web — карта «качество ↔ цена/скорость» (вторичный, наглядный вид под рейтингом).
   Управляется снаружи (metric задаёт Economy). Зона «выгода» (дёшево+сильно) подсвечена,
   все точки подписаны, без абстрактного пунктира-Парето. Точка → страница модели. */
import React from 'react';
import { fmtRub } from '../../lib/insights.js';

const VB_W = 920, VB_H = 470;
const M = { l: 58, r: 26, t: 26, b: 50 };
const PW = VB_W - M.l - M.r;
const PH = VB_H - M.t - M.b;

export const METRICS = {
  cost: { key: 'runCost', label: 'стоимость полного прогона', log: true, fmt: fmtRub, better: 'дешевле' },
  time: { key: 'avgTime', label: 'среднее время на задачу', log: false, fmt: (v) => `${v}с`, better: 'быстрее' },
};

// Парето-оптимальные: никто не лучше И по качеству, И по метрике (меньше = лучше)
export function paretoSet(pts) {
  const set = new Set();
  for (const p of pts) {
    const dominated = pts.some((o) => o.id !== p.id && o.x <= p.x && o.q >= p.q && (o.x < p.x || o.q > p.q));
    if (!dominated) set.add(p.id);
  }
  return set;
}

export function QuadrantView({ models = [], navigate = () => {}, metric = 'cost' }) {
  const [hover, setHover] = React.useState(null);
  const cfg = METRICS[metric];

  const pts = models
    .filter((m) => m.qOverall != null && m.econ && m.econ[cfg.key] != null && m.econ[cfg.key] > 0)
    .map((m) => ({ id: m.id, name: m.name, q: m.qOverall, x: m.econ[cfg.key], econ: m.econ }));
  if (pts.length < 2) return null;

  const tx = (v) => (cfg.log ? Math.log10(v) : v);
  const xs = pts.map((p) => tx(p.x));
  const qs = pts.map((p) => p.q);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const xpad = (x1 - x0) * 0.1 || 1;
  const yMin = Math.floor(Math.min(...qs)), yMax = 10;
  const sx = (v) => M.l + ((tx(v) - (x0 - xpad)) / ((x1 + xpad) - (x0 - xpad))) * PW;
  const sy = (v) => M.t + (1 - (v - yMin) / (yMax - yMin)) * PH;

  const front = paretoSet(pts);

  const xticks = cfg.log
    ? [0.003, 0.01, 0.03, 0.1, 0.3, 1, 3].filter((v) => tx(v) >= x0 - xpad && tx(v) <= x1 + xpad)
    : (() => { const a = []; for (let v = Math.ceil(x0 / 5) * 5; v <= x1 + xpad; v += 5) a.push(v); return a; })();
  const yticks = []; for (let v = yMin; v <= yMax; v += (yMax - yMin > 6 ? 2 : 1)) yticks.push(v);

  return (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }}>
      {/* зона выгоды — мягкий градиент из левого-верхнего угла, без рамки */}
      <defs>
        <linearGradient id="prism-good-zone" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--axis-o)" stopOpacity="0.14" />
          <stop offset="55%" stopColor="var(--axis-o)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x={M.l} y={M.t} width={PW} height={PH} fill="url(#prism-good-zone)" />
      <text x={M.l + 12} y={M.t + 20} fontFamily="var(--font-mono)" fontSize="11" fontWeight="700" fill="var(--axis-o)" opacity="0.75">выгода ↖ дёшево + сильно</text>

      {/* сетка + тики Y */}
      {yticks.map((v) => (
        <g key={`y${v}`}>
          <line x1={M.l} y1={sy(v)} x2={M.l + PW} y2={sy(v)} stroke="var(--line)" strokeWidth="1" strokeDasharray="2 4" />
          <text x={M.l - 10} y={sy(v) + 4} textAnchor="end" fontFamily="var(--font-mono)" fontSize="11" fill="var(--ink-400)">{v}</text>
        </g>
      ))}
      {xticks.map((v) => (
        <text key={`x${v}`} x={sx(v)} y={M.t + PH + 22} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="11" fill="var(--ink-400)">{cfg.fmt(v)}</text>
      ))}
      <text x={M.l + PW / 2} y={VB_H - 6} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="11.5" fill="var(--ink-300)">← {cfg.better} · {cfg.label} →</text>
      <text x={16} y={M.t + PH / 2} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="11.5" fill="var(--ink-300)" transform={`rotate(-90 16 ${M.t + PH / 2})`}>выше = качественнее →</text>

      {/* точки: оптимум — зелёные с подписью; остальные — тихие точки, имя по наведению */}
      {pts.map((p) => {
        const on = front.has(p.id);
        const isHover = hover === p.id;
        const cx = sx(p.x), cy = sy(p.q);
        const labelLeft = cx > M.l + PW * 0.7; // у правого края — подпись слева
        const showLabel = on || isHover;
        return (
          <g key={p.id} style={{ cursor: 'pointer' }}
            onMouseEnter={() => setHover(p.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate('model', p.id)}>
            <title>{`${p.name} · Q ${p.q.toFixed(2)} · ${cfg.fmt(p.x)}`}</title>
            {/* увеличенная прозрачная мишень для удобного наведения на мелкие точки */}
            <circle cx={cx} cy={cy} r={11} fill="transparent" />
            <circle cx={cx} cy={cy} r={isHover ? 6.5 : on ? 5.5 : 3.5} fill={on ? 'var(--axis-o)' : 'var(--ink-400)'} stroke="var(--surface)" strokeWidth="1.5" opacity={on || isHover ? 1 : 0.55} />
            {showLabel && (
              <text x={labelLeft ? cx - 10 : cx + 10} y={cy + 3.5} textAnchor={labelLeft ? 'end' : 'start'} fontFamily="var(--font-mono)" fontSize="11" fontWeight={on ? 600 : 500} fill={isHover ? 'var(--ink-100)' : 'var(--ink-200)'}>{p.name}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
