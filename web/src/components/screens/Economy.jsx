/* PRISM web — вкладка «Экономика»: понятный рейтинг цена/качество.
   Рейтинг читается сверху вниз: каждая модель подписана, полосы качества и цены,
   значок «оптимум» = нет варианта одновременно дешевле/быстрее И сильнее. */
import React from 'react';
import { Badge } from '../core/Badge.jsx';
import { VendorLogo } from '../prism/VendorLogo.jsx';
import { METRICS, paretoSet } from './Quadrant.jsx';
import { TableExport, EconomyTableSvg } from '../prism/LeaderChart.jsx';
import { useIsMobile } from '../../lib/useMediaQuery.js';

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

// мобильная строка рейтинга: модель + бейдж сверху, полосы качества и цены парой под ними —
// без горизонтального скролла и без шапки-таблицы (подписи живут в самих полосах)
function MobileRow({ p, cfg, maxX, qMax, optimum, dominator, first, onClick }) {
  return (
    <div role="button" tabIndex={0} onClick={onClick}
      style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 12px', cursor: 'pointer',
        borderTop: first ? 'none' : '1px solid var(--line)',
        background: optimum ? 'var(--top-tint)' : 'transparent',
        boxShadow: optimum ? 'inset 2px 0 0 var(--axis-o)' : 'none', opacity: optimum ? 1 : 0.92 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
        <VendorLogo vendor={p.vendor} name={p.name} size={28} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--ink-100)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--ink-400)', marginTop: 1 }}>{dominator ? `уступает ${dominator}` : p.family}</div>
        </div>
        {optimum
          ? <Badge tone="ok" dot={false} size="sm">оптимум</Badge>
          : <span style={{ color: 'var(--ink-400)', fontSize: 19, lineHeight: 1 }}>›</span>}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Bar frac={p.q / qMax} color={qColor(p.q)} label={`Q ${p.q.toFixed(2)}`} />
        <Bar frac={p.x / maxX} color="var(--ink-300)" label={cfg.fmt(p.x)} sub={p.hint} />
      </div>
    </div>
  );
}

// подсказки для крайних значений
const HINT_MIN = { cost: 'дешевле всех', time: 'быстрее всех', tokens: 'экономнее всех' };
const HINT_MAX = { cost: 'дороже всех', time: 'медленнее всех', tokens: 'прожорливее всех' };

/* Рейтинг «Экономики» одним списком: оптимум первыми (по Q), затем остальные (по Q).
   Считается один раз на вид — из него живёт и таблица на экране, и выгружаемая картинка. */
function buildRanking(models, metric) {
  const cfg = METRICS[metric];
  const pts = models
    .filter((m) => m.qOverall != null && m.econ && m.econ[cfg.key] != null && m.econ[cfg.key] > 0)
    .map((m) => ({ id: m.id, name: m.name, family: m.family, vendor: m.vendor, q: m.qOverall, x: m.econ[cfg.key] }));
  if (!pts.length) return { cfg, rows: [], maxX: 1, qMax: 1 };

  const front = paretoSet(pts);
  const maxX = Math.max(...pts.map((p) => p.x));
  const minX = Math.min(...pts.map((p) => p.x));
  const qMax = Math.max(...pts.map((p) => p.q));
  for (const p of pts) {
    if (p.x === minX) p.hint = HINT_MIN[metric];
    else if (p.x === maxX) p.hint = HINT_MAX[metric];
  }
  const dominatorOf = (p) => {
    const doms = pts.filter((o) => o.id !== p.id && o.x <= p.x && o.q >= p.q && (o.x < p.x || o.q > p.q));
    if (!doms.length) return null;
    return doms.sort((a, b) => b.q - a.q)[0].name; // самый качественный из тех, кто доминирует
  };

  const optimum = pts.filter((p) => front.has(p.id)).sort((a, b) => b.q - a.q);
  const rest = pts.filter((p) => !front.has(p.id)).sort((a, b) => b.q - a.q);
  const rows = [
    ...optimum.map((p) => ({ ...p, optimum: true, dominator: null })),
    ...rest.map((p) => ({ ...p, optimum: false, dominator: dominatorOf(p) })),
  ];
  return { cfg, rows, maxX, qMax };
}

function ValueRanking({ rows, cfg, maxX, qMax, navigate, metric }) {
  const isMobile = useIsMobile();
  if (!rows.length) return <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>нет данных.</p>;

  const optimum = rows.filter((p) => p.optimum);
  const rest = rows.filter((p) => !p.optimum);

  const head = { fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)' };

  if (isMobile) {
    return (
      <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
        {optimum.map((p, i) => <MobileRow key={p.id} p={p} cfg={cfg} maxX={maxX} qMax={qMax} optimum dominator={null} first={i === 0} onClick={() => navigate('model', p.id)} />)}
        {rest.length > 0 && (
          <div style={{ padding: '9px 12px', background: 'var(--surface-sunken)', borderTop: '1px solid var(--line)' }}>
            <span style={{ ...head, color: 'var(--ink-400)' }}>остальные — есть вариант дешевле и сильнее</span>
          </div>
        )}
        {rest.map((p) => <MobileRow key={p.id} p={p} cfg={cfg} maxX={maxX} qMax={qMax} optimum={false} dominator={p.dominator} onClick={() => navigate('model', p.id)} />)}
      </div>
    );
  }

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflowX: 'auto' }}>
     <div style={{ minWidth: 600 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '30px minmax(150px,1.4fr) minmax(120px,1fr) minmax(120px,1fr) 104px', gap: 16, alignItems: 'center', padding: '11px 18px', background: 'var(--surface-sunken)', borderBottom: '1px solid var(--line)' }}>
        <span />
        <span style={head}>модель</span>
        <span style={head}>качество</span>
        <span style={head}>{metric === 'cost' ? 'цена / генерация' : metric === 'time' ? 'время / задача' : 'токенов / генерация'}</span>
        <span style={{ ...head, textAlign: 'right' }}>выгода</span>
      </div>
      {optimum.map((p) => <Row key={p.id} p={p} cfg={cfg} maxX={maxX} qMax={qMax} optimum dominator={null} onClick={() => navigate('model', p.id)} />)}
      {rest.length > 0 && (
        <div style={{ padding: '9px 18px', background: 'var(--surface-sunken)', borderTop: '1px solid var(--line)' }}>
          <span style={{ ...head, color: 'var(--ink-400)' }}>остальные — есть вариант дешевле и сильнее</span>
        </div>
      )}
      {rest.map((p) => <Row key={p.id} p={p} cfg={cfg} maxX={maxX} qMax={qMax} optimum={false} dominator={p.dominator} onClick={() => navigate('model', p.id)} />)}
     </div>
    </div>
  );
}

// подпись над таблицей — что именно меряет вид (как на вкладках A/B)
const LEAD = {
  cost: <>Сколько стоит <b style={{ color: 'var(--ink-200)' }}>один ответ</b> модели: прайс-лист провайдера × реально сгенерированные токены, в среднем по всем задачам. Q — итоговый балл SMOP, взвешен по числу задач. «Оптимум» — нет модели одновременно дешевле и сильнее.</>,
  time: <>Сколько модель отвечает на <b style={{ color: 'var(--ink-200)' }}>одну задачу</b>, секунды. Это замер прогона: зависит от загрузки провайдера и длины ответа, на баллы не влияет. «Оптимум» — нет модели одновременно быстрее и сильнее.</>,
  tokens: <>Сколько токенов (вход + выход) уходит на <b style={{ color: 'var(--ink-200)' }}>один ответ</b>. От тарифа не зависит, поэтому сравнимо между провайдерами: мало токенов ≠ дёшево. «Оптимум» — нет модели одновременно экономнее и сильнее.</>,
};

// сноска под таблицей — оговорки к цифрам
const FOOT = {
  cost: 'цена генерации — средняя стоимость одного ответа модели (по всем задачам) = прайс-лист провайдера × реально сгенерированные токены. Зарубежные — тариф OpenRouter, Sber и Yandex — прайс-лист провайдера. Q взвешен по числу задач.',
  time: 'время — сумма ожидания ответа от провайдера, делённая на число задач. Замерено в одном прогоне и не усреднялось по повторам, поэтому годится для порядка величин, а не для точного сравнения близких значений. Исполнение кода в песочнице сюда не входит.',
  tokens: '«токенов на генерацию» — среднее число токенов (вход + выход) на один ответ. Меньше = лаконичнее, и не зависит от тарифа. Важно: мало токенов ≠ дёшево — дорогая модель бывает экономной по токенам (например, GPT‑5.5 краток, но токен у него дорогой). У рассуждающих моделей размышления попадают в выход и раздувают счёт.',
};

export function EconomyView({ models = [], navigate = () => {}, meta = {} }) {
  const [metric, setMetric] = React.useState('cost');
  const [scope, setScope] = React.useState('all'); // охват: по умолчанию ВСЕ модели (Топ-10 опционален)
  const { cfg, rows, maxX, qMax } = React.useMemo(() => buildRanking(models, metric), [models, metric]);
  const shown = scope === 'all' ? rows : rows.slice(0, 10);
  return (
    <div>
      {/* отступ до таблицы 16 — как у переключателя видов на вкладках A/B */}
      <div style={{ marginBottom: 16 }}>
        <Segmented items={[{ key: 'cost', label: 'Цена' }, { key: 'time', label: 'Скорость' }, { key: 'tokens', label: 'Токены' }]} value={metric} onChange={setMetric} />
      </div>

      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-400)', lineHeight: 1.5 }}>{LEAD[metric]}</p>

      <TableExport scope={scope} setScope={setScope} count={rows.length} name={`prism_econ_${metric}_${scope}`}
        render={(ref, C) => <EconomyTableSvg svgRef={ref} rows={shown} metric={metric} fmt={cfg.fmt} meta={meta} C={C} />} />

      <ValueRanking rows={shown} cfg={cfg} maxX={maxX} qMax={qMax} navigate={navigate} metric={metric} />

      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)', margin: '22px 0 0' }}>{FOOT[metric]}</p>
    </div>
  );
}
