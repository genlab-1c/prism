/* PRISM web — вкладка «Экономика»: понятный рейтинг цена/качество (основной вид)
   + наглядная карта-разброс ниже. Общий переключатель Цена/Скорость управляет обоими.
   Рейтинг читается сверху вниз: каждая модель подписана, полосы качества и цены,
   значок «оптимум» = нет варианта одновременно дешевле/быстрее И сильнее. */
import React from 'react';
import { Badge } from '../core/Badge.jsx';
import { VendorLogo } from '../prism/VendorLogo.jsx';
import { METRICS, paretoSet, QuadrantView } from './Quadrant.jsx';

function Segmented({ items, value, onChange }) {
  return (
    <div style={{ display: 'inline-flex', gap: 2, padding: 3, background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)' }}>
      {items.map((it) => {
        const on = it.key === value;
        return <button key={it.key} onClick={() => onChange(it.key)} style={{ border: 'none', cursor: 'pointer', borderRadius: 'var(--radius-sm)', padding: '7px 15px', fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: on ? 600 : 500, background: on ? 'var(--surface-raised)' : 'transparent', color: on ? 'var(--ink-100)' : 'var(--ink-400)' }}>{it.label}</button>;
      })}
    </div>
  );
}

const qColor = (q) => (q >= 8 ? 'var(--axis-o)' : q >= 6 ? 'var(--brand)' : q >= 4 ? 'var(--axis-p)' : 'var(--danger)');

// горизонтальная полоса: доля 0..1, цвет; подпись значения справа
function Bar({ frac, color, label, sub }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 13.5, fontWeight: 700, color: 'var(--ink-100)' }}>{label}</span>
        {sub && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>{sub}</span>}
      </div>
      <div style={{ height: 6, borderRadius: 'var(--radius-pill)', background: 'var(--track-bg)', overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(2, Math.min(100, frac * 100))}%`, height: '100%', background: color, borderRadius: 'var(--radius-pill)' }} />
      </div>
    </div>
  );
}

function Row({ p, cfg, maxX, qMax, optimum, dominator, onClick }) {
  const [h, setH] = React.useState(false);
  return (
    <div role="button" tabIndex={0} onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)} onClick={onClick}
      style={{ display: 'grid', gridTemplateColumns: '30px minmax(150px,1.4fr) minmax(120px,1fr) minmax(120px,1fr) 104px', gap: 16, alignItems: 'center', padding: '13px 18px', cursor: 'pointer', borderTop: '1px solid var(--line)', background: h ? 'var(--surface-raised)' : (optimum ? 'var(--top-tint)' : 'transparent'), boxShadow: optimum && !h ? 'inset 2px 0 0 var(--axis-o)' : 'none', transition: 'background var(--dur) var(--ease)', opacity: optimum ? 1 : 0.92 }}>
      <VendorLogo vendor={p.vendor} name={p.name} size={28} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--ink-100)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
        {dominator
          ? <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--ink-400)', marginTop: 1 }}>уступает {dominator}</div>
          : <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--ink-400)', marginTop: 1 }}>{p.family}</div>}
      </div>
      <Bar frac={p.q / qMax} color={qColor(p.q)} label={`Q ${p.q.toFixed(2)}`} />
      <Bar frac={cfg.log ? p.x / maxX : p.x / maxX} color="var(--ink-300)" label={cfg.fmt(p.x)} sub={p.hint} />
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {optimum
          ? <Badge tone="ok" dot={false} size="sm">оптимум</Badge>
          : <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>—</span>}
      </div>
    </div>
  );
}

function ValueRanking({ models, navigate, metric }) {
  const cfg = METRICS[metric];
  const pts = models
    .filter((m) => m.qOverall != null && m.econ && m.econ[cfg.key] != null && m.econ[cfg.key] > 0)
    .map((m) => ({ id: m.id, name: m.name, family: m.family, vendor: m.vendor, q: m.qOverall, x: m.econ[cfg.key] }));
  if (!pts.length) return <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>нет данных.</p>;

  const front = paretoSet(pts);
  const maxX = Math.max(...pts.map((p) => p.x));
  const minX = Math.min(...pts.map((p) => p.x));
  const qMax = Math.max(...pts.map((p) => p.q));
  // подсказки для крайних значений
  for (const p of pts) {
    if (p.x === minX) p.hint = metric === 'cost' ? 'дешевле всех' : 'быстрее всех';
    else if (p.x === maxX) p.hint = metric === 'cost' ? 'дороже всех' : 'медленнее всех';
  }
  const dominatorOf = (p) => {
    const doms = pts.filter((o) => o.id !== p.id && o.x <= p.x && o.q >= p.q && (o.x < p.x || o.q > p.q));
    if (!doms.length) return null;
    return doms.sort((a, b) => b.q - a.q)[0].name; // самый качественный из тех, кто доминирует
  };

  // порядок: оптимум первыми (по Q), затем остальные (по Q)
  const optimum = pts.filter((p) => front.has(p.id)).sort((a, b) => b.q - a.q);
  const rest = pts.filter((p) => !front.has(p.id)).sort((a, b) => b.q - a.q);

  const head = { fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)' };
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflowX: 'auto' }}>
     <div style={{ minWidth: 600 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '30px minmax(150px,1.4fr) minmax(120px,1fr) minmax(120px,1fr) 104px', gap: 16, alignItems: 'center', padding: '11px 18px', background: 'var(--surface-sunken)', borderBottom: '1px solid var(--line)' }}>
        <span />
        <span style={head}>модель</span>
        <span style={head}>качество</span>
        <span style={head}>{metric === 'cost' ? 'цена / генерация' : 'время / задача'}</span>
        <span style={{ ...head, textAlign: 'right' }}>выгода</span>
      </div>
      {optimum.map((p) => <Row key={p.id} p={p} cfg={cfg} maxX={maxX} qMax={qMax} optimum dominator={null} onClick={() => navigate('model', p.id)} />)}
      {rest.length > 0 && (
        <div style={{ padding: '9px 18px', background: 'var(--surface-sunken)', borderTop: '1px solid var(--line)' }}>
          <span style={{ ...head, color: 'var(--ink-400)' }}>остальные — есть вариант дешевле и сильнее</span>
        </div>
      )}
      {rest.map((p) => <Row key={p.id} p={p} cfg={cfg} maxX={maxX} qMax={qMax} optimum={false} dominator={dominatorOf(p)} onClick={() => navigate('model', p.id)} />)}
     </div>
    </div>
  );
}

export function EconomyView({ models = [], navigate = () => {} }) {
  const [metric, setMetric] = React.useState('cost');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink-100)' }}>Что выгоднее: качество за {metric === 'cost' ? 'деньги' : 'время'}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)', marginTop: 3 }}>
            <span style={{ color: 'var(--axis-o)' }}>оптимум</span> = нет модели одновременно {metric === 'cost' ? 'дешевле' : 'быстрее'} И сильнее · отсортировано по качеству
          </div>
        </div>
        <Segmented items={[{ key: 'cost', label: 'Цена' }, { key: 'time', label: 'Скорость' }]} value={metric} onChange={setMetric} />
      </div>

      <ValueRanking models={models} navigate={navigate} metric={metric} />

      {/* наглядная карта-разброс — вторичный вид для тех, кто хочет общую картину */}
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-100)', marginBottom: 4 }}>Карта разброса</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)', marginBottom: 12 }}>выше и левее — выгоднее · <span style={{ color: 'var(--axis-o)' }}>зелёные</span> = оптимум (подписаны) · наведи на точку — имя, клик — открыть</div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', padding: '18px 20px' }}>
          <QuadrantView models={models} navigate={navigate} metric={metric} />
        </div>
      </div>

      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)', margin: 0 }}>цена генерации — средняя стоимость одного ответа модели (по всем задачам) = прайс-лист провайдера × реально сгенерированные токены. Зарубежные — тариф OpenRouter, Sber и Yandex — прайс-лист провайдера. Q взвешен по числу задач.</p>
    </div>
  );
}
