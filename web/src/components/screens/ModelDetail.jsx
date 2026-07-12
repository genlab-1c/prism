/* PRISM web — экран модели: профиль (оси A/B) + браузер генераций.
   Профиль — из DS ModelDetailScreen; «Пример задачи» заменён на настоящий
   браузер кода: список задач → реальный BSL-ответ модели (подсветка на билде).
   Код грузится лениво из public/data/gen/<id>.json по клику на модель. */
import React from 'react';
import { Icon } from '../chrome/Chrome.jsx';
import { VendorLogo } from '../prism/VendorLogo.jsx';
import { Button } from '../core/Button.jsx';
import { Tag } from '../core/Tag.jsx';
import { ScoreBar } from '../prism/ScoreBar.jsx';
import { ScoreVector } from '../prism/ScoreVector.jsx';
import { QScore } from '../prism/QScore.jsx';
import { NarrativeCard, ShareBar } from '../prism/NarrativeCard.jsx';
import { fmtRub } from '../../lib/insights.js';
import { useIsMobile } from '../../lib/useMediaQuery.js';

const BASE = import.meta.env.BASE_URL;

// исход задачи → подпись и цвет (как в воронке)
const OUTCOME = {
  solved: ['решено', 'var(--axis-o)'],
  wrong: ['неверный ответ', '#d8b13e'],
  runtime: ['ошибка выполнения', '#dd7a3b'],
  compile: ['не компилируется', 'var(--danger)'],
  unknown: ['—', 'var(--ink-400)'],
};
const outcomeColor = (o) => (OUTCOME[o] || OUTCOME.unknown)[1];

// Разбор оценки: по каждой оси — балл, человеческая причина, метрика, за что списано.
const AXC = {
  S: ['var(--axis-s)', 'var(--axis-s-soft)'], M: ['var(--axis-m)', 'var(--axis-m-soft)'],
  O: ['var(--axis-o)', 'var(--axis-o-soft)'], P: ['var(--axis-p)', 'var(--axis-p-soft)'],
};
function DeltaPill({ tag, score }) {
  let label = 'полный балл', color = 'var(--axis-o)', bg = 'var(--axis-o-soft)', bd = 'none';
  if (tag === 'warn') { label = 'частично'; color = 'var(--axis-p)'; bg = 'var(--axis-p-soft)'; }
  else if (tag === 'na') { label = 'не измерено'; color = 'var(--ink-400)'; bg = 'var(--surface-sunken)'; bd = '1px solid var(--line)'; }
  else if (tag === 'minus') { label = `−${Math.round((10 - (score ?? 0)) * 10) / 10}`; color = 'var(--danger)'; bg = 'var(--danger-soft)'; }
  return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, fontWeight: 600, padding: '3px 9px', borderRadius: 999, color, background: bg, border: bd, whiteSpace: 'nowrap' }}>{label}</span>;
}
function ScoreBreakdown({ items = [] }) {
  if (!items.length) return null;
  return (
    <div style={{ padding: '13px 16px', borderBottom: '1px solid var(--line)' }}>
      <div className="prism-eyebrow" style={{ marginBottom: 4 }}>разбор оценки · за что балл</div>
      {items.map((it) => {
        const na = it.score == null, [c] = AXC[it.ax] || [];
        const scColor = na ? 'var(--ink-400)' : it.tag === 'full' ? 'var(--axis-o)' : it.tag === 'minus' ? 'var(--danger)' : 'var(--ink-100)';
        return (
          <div key={it.ax} style={{ display: 'grid', gridTemplateColumns: '54px 1fr auto', gap: 14, alignItems: 'center', padding: '11px 0', borderTop: '1px solid var(--line-soft)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <span style={{ width: 22, height: 22, borderRadius: 6, background: AXC[it.ax]?.[1], color: c, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11.5 }}>{it.ax}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 15.5, fontWeight: 600, color: scColor }}>{na ? 'N/A' : it.score}</span>
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-100)', lineHeight: 1.3 }}>{it.head}</div>
              <div style={{ fontSize: 12, color: 'var(--ink-300)', marginTop: 2, lineHeight: 1.4 }}>{it.metric}</div>
            </div>
            <DeltaPill tag={it.tag} score={it.score} />
          </div>
        );
      })}
    </div>
  );
}

function CategoryPanel({ title, sub, q, scores, axisOrder }) {
  if (!scores) return null;
  return (
    <div style={{ flex: 1, minWidth: 280, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink-100)' }}>{title}</div>
          <div style={{ fontSize: 12.5, color: 'var(--ink-400)', marginTop: 2 }}>{sub}</div>
        </div>
        <QScore value={q ?? 0} size="md" label="Q" style={{ alignItems: 'flex-end' }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
        {axisOrder.map((a) => <ScoreBar key={a} axis={a} value={scores[a] ?? 0} />)}
      </div>
    </div>
  );
}

function TaskItem({ t, active, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid', gridTemplateColumns: '8px 40px 1fr auto', gap: 9, alignItems: 'center', width: '100%',
        textAlign: 'left', cursor: 'pointer', border: 'none', borderLeft: `2px solid ${active ? 'var(--brand)' : 'transparent'}`,
        background: active ? 'var(--surface-raised)' : (hover ? 'var(--hover-overlay)' : 'transparent'),
        padding: '9px 12px', transition: 'background var(--dur-fast) var(--ease)',
      }}>
      <span title={(OUTCOME[t.diag?.outcome] || OUTCOME.unknown)[0]} style={{ width: 8, height: 8, borderRadius: '50%', background: outcomeColor(t.diag?.outcome) }} />
      <Tag color={t.category === 'B' ? 'p' : 'neutral'}>{t.taskId}</Tag>
      <span style={{ fontSize: 12.5, color: active ? 'var(--ink-100)' : 'var(--ink-300)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.taskName}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 12.5, fontWeight: 600, color: t.empty ? 'var(--ink-400)' : 'var(--ink-200)' }}>{t.scores.Q != null ? t.scores.Q.toFixed(1) : '—'}</span>
    </button>
  );
}

const fmtTokens = (n) => (n == null ? '—' : n < 1000 ? `${n}` : `${(n / 1000).toFixed(1)}k`);
const fmtTime = (t) => (t == null ? '—' : `${t.toFixed(1)}с`);
const fmtCost = fmtRub; // стоимость показываем в рублях
const Sep = () => <span style={{ color: 'var(--line)' }}>·</span>;

/* ---------- вьюер метаданных синтетической базы 1С — дерево как в Конфигураторе ---------- */
const KIND_LABEL = {
  catalogs: 'Справочники', documents: 'Документы', accumulation_registers: 'Регистры накопления',
  information_registers: 'Регистры сведений', accounting_registers: 'Регистры бухгалтерии',
  charts_of_accounts: 'Планы счетов', charts_of_characteristic_types: 'Планы видов характеристик',
  enums: 'Перечисления', constants: 'Константы',
};
const GROUP_LABEL = { dimensions: 'Измерения', resources: 'Ресурсы', attributes: 'Реквизиты' };
const fmtType = (v) => {
  if (v == null) return '';
  if (typeof v !== 'object') return String(v);
  let s = v.type || '';
  if (v.length != null) s += `(${v.length}${v.precision != null ? `,${v.precision}` : ''})`;
  return s || JSON.stringify(v);
};

// одна строка дерева: треугольник (если есть потомки) + имя + бэйджи + тип; сворачивается по клику
function TreeNode({ depth = 0, name, nameColor, badges = [], type, defaultOpen = true, children }) {
  const kids = React.Children.toArray(children).filter(Boolean);
  const has = kids.length > 0;
  const [open, setOpen] = React.useState(defaultOpen);
  const [hover, setHover] = React.useState(false);
  return (
    <div>
      <div onClick={has ? () => setOpen((o) => !o) : undefined}
        onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
        style={{ display: 'flex', alignItems: 'center', gap: 7, minHeight: 24, borderRadius: 'var(--radius-xs)',
          padding: '2px 8px', paddingLeft: 8 + depth * 18, cursor: has ? 'pointer' : 'default',
          background: hover ? 'var(--hover-overlay)' : 'transparent', fontFamily: 'var(--font-mono)', fontSize: 12.5 }}>
        <span style={{ width: 10, flex: 'none', textAlign: 'center', fontSize: 9, color: 'var(--ink-400)',
          transform: open ? 'rotate(90deg)' : 'none', transition: 'transform var(--dur-fast) var(--ease)', visibility: has ? 'visible' : 'hidden' }}>▶</span>
        <span style={{ color: nameColor || 'var(--ink-200)', fontWeight: nameColor ? 600 : 500, whiteSpace: 'nowrap' }}>{name}</span>
        {badges.map((b) => <span key={b} style={{ fontSize: 10, color: 'var(--axis-p)', background: 'var(--axis-p-soft)', borderRadius: 'var(--radius-xs)', padding: '1px 6px' }}>{b}</span>)}
        {type && <span style={{ color: 'var(--ink-400)', marginLeft: 2 }}>{type}</span>}
      </div>
      {open && has && <div>{kids}</div>}
    </div>
  );
}

// объект конфигурации: бэйджи (иерархия/тип регистра/периодичность) + группы полей + табличные части
function ObjectNode({ depth, name, def = {} }) {
  const badges = [];
  if (def.hierarchical) badges.push('иерархия');
  if (def.register_type) badges.push(def.register_type === 'Balance' ? 'остатки' : def.register_type === 'Turnovers' ? 'обороты' : String(def.register_type));
  if (def.periodicity) badges.push(`период: ${def.periodicity}`);
  const groups = ['dimensions', 'resources', 'attributes'].filter((g) => def[g] && Object.keys(def[g]).length);
  const ts = def.tabular_sections || {};
  return (
    <TreeNode depth={depth} name={name} nameColor="var(--axis-p)" badges={badges}>
      {Array.isArray(def.registers) && def.registers.length > 0 &&
        <TreeNode depth={depth + 1} name="движения" type={`→ ${def.registers.join(', ')}`} />}
      {groups.map((g) => (
        <TreeNode key={g} depth={depth + 1} name={GROUP_LABEL[g]} nameColor="var(--ink-300)">
          {Object.entries(def[g]).map(([k, v]) => <TreeNode key={k} depth={depth + 2} name={k} type={fmtType(v)} />)}
        </TreeNode>
      ))}
      {Object.entries(ts).map(([tname, tdef]) => (
        <TreeNode key={tname} depth={depth + 1} name={tname} nameColor="var(--axis-p)" badges={['таб. часть']}>
          {Object.entries(tdef.attributes || {}).map(([k, v]) => <TreeNode key={k} depth={depth + 2} name={k} type={fmtType(v)} />)}
        </TreeNode>
      ))}
    </TreeNode>
  );
}

function ConfigView({ config }) {
  const known = Object.keys(KIND_LABEL);
  const keys = [...known.filter((k) => config[k]), ...Object.keys(config).filter((k) => !known.includes(k) && config[k] && typeof config[k] === 'object')];
  return (
    <div style={{ padding: '12px 8px' }}>
      {keys.map((k) => {
        const objs = config[k];
        if (!objs || typeof objs !== 'object' || !Object.keys(objs).length) return null;
        return (
          <TreeNode key={k} depth={0} name={KIND_LABEL[k] || k} nameColor="var(--ink-100)">
            {Object.entries(objs).map(([name, def]) => <ObjectNode key={name} depth={1} name={name} def={def || {}} />)}
          </TreeNode>
        );
      })}
    </div>
  );
}

/* ---------- вьюер тестов категории A (вход → ожидание) ---------- */
function MiniTable({ columns = [], rows = [] }) {
  return (
    <table style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>
      <thead><tr>{columns.map((c) => <th key={c} style={{ textAlign: 'left', padding: '3px 9px', color: 'var(--ink-400)', borderBottom: '1px solid var(--line)', fontWeight: 600 }}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((cell, j) => <td key={j} style={{ padding: '3px 9px', color: 'var(--ink-200)', borderBottom: '1px solid var(--line-soft)' }}>{String(cell)}</td>)}</tr>)}</tbody>
    </table>
  );
}
function Val({ v }) {
  if (v && typeof v === 'object' && v.__table__) return <MiniTable columns={v.__table__.columns} rows={v.__table__.rows} />;
  return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-200)' }}>{typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}</span>;
}
// Тест — одной строкой: статус · номер · аргументы → ожидание. Упавшие (из diag.failedIdx) подсвечены.
function TestCases({ cases = [], failed = [], passed = null, total = null }) {
  const fset = new Set(failed);
  const allPass = passed != null && total != null && passed === total;
  // «pass» уверенно, если failedIdx покрывает ВСЕ провалы (прошло + упало = всего) — тогда остальные точно зелёные
  const reliable = passed != null && total != null && (allPass || passed + failed.length === total);
  const mark = (i) => (fset.has(i) ? 'fail' : reliable ? 'pass' : null);
  const COL = { fail: 'var(--danger)', pass: 'var(--axis-o)' };
  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
      {passed != null && total != null && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)', padding: '0 4px 4px' }}>
          прошло <b style={{ color: allPass ? 'var(--axis-o)' : 'var(--ink-200)' }}>{passed}/{total}</b>
          {failed.length ? <> · упал на тестах <b style={{ color: 'var(--danger)' }}>{failed.map((i) => i + 1).join(', ')}</b></> : null}
        </div>
      )}
      {cases.map((c, i) => {
        const st = mark(i);
        const col = st ? COL[st] : 'var(--ink-400)';
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '9px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--line)', background: st === 'fail' ? 'var(--danger-soft)' : 'var(--surface-sunken)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 62, flex: 'none' }}>
              {st && <span style={{ width: 8, height: 8, borderRadius: '50%', background: col }} />}
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, fontWeight: 600, color: st ? col : 'var(--ink-300)' }}>тест {i + 1}</span>
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', minWidth: 0, flex: 1 }}>
              {(c.args || []).map((a, j) => <Val key={j} v={a} />)}
              <span style={{ color: 'var(--axis-o)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>→</span>
              <Val v={c.expected} />
            </div>
            {st && <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: col }}>{st === 'fail' ? 'не прошёл' : 'пройден'}</span>}
          </div>
        );
      })}
    </div>
  );
}

function CodeTab({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '11px 4px', marginRight: 18, borderBottom: `2px solid ${active ? 'var(--brand)' : 'transparent'}`, fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: active ? 600 : 500, color: active ? 'var(--ink-100)' : 'var(--ink-400)' }}>{label}</button>
  );
}

// Панель кода: номера строк (в CSS), подсветка строк ошибок + прокрутка к строке.
// focus={line, seq} — клик по конкретной ошибке; seq меняется на каждый клик, чтобы повтор срабатывал.
function CodeView({ html, errorLines = [], focus = null }) {
  const ref = React.useRef(null);
  const scrollToLine = (root, ln) => { // прокрутка ВНУТРИ панели (overflow auto) — страницу не двигаем
    const top = ln.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop;
    root.scrollTop = Math.max(0, top - root.clientHeight / 2);
  };
  React.useEffect(() => { // новый код → пометить строки ошибок; авто-скролл к первой (если нет явного клика)
    const root = ref.current;
    if (!root) return;
    const lines = root.querySelectorAll('.line');
    let first = null;
    for (const n of errorLines) {
      const ln = lines[n - 1];
      if (ln) { ln.classList.add('code-error-line'); if (!first) first = ln; }
    }
    if (first && !focus) scrollToLine(root, first);
  }, [html]);
  React.useEffect(() => { // клик по ошибке → прокрутить к её строке + короткая вспышка
    const root = ref.current;
    if (!root || !focus) return;
    const ln = root.querySelectorAll('.line')[focus.line - 1];
    if (!ln) return;
    scrollToLine(root, ln);
    ln.classList.add('code-focus-line');
    const t = setTimeout(() => ln.classList.remove('code-focus-line'), 1300);
    return () => clearTimeout(t);
  }, [focus, html]);
  return <div className="code-pane" ref={ref} dangerouslySetInnerHTML={{ __html: html }} />;
}

// метаданные генерации: подпись сверху, значение снизу (читаемее, чем «1.0k ток · 4.9с»)
function MetaItem({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, lineHeight: 1.2 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 12.5 }}>{children}</span>
    </div>
  );
}

// нагрузочный тест: как растёт «стоимость» решения с размером входа/базы — график + человеческое пояснение
function PerfChart({ perf }) {
  const { sizes, series, growth, pOpt, growthF, pOptF, unit, xlabel } = perf;
  const isB = unit.indexOf('СУБД') >= 0;            // B — обращения к СУБД; A — операции
  const grow = series.length >= 2 && series[0] ? series[series.length - 1] / series[0] : null; // во сколько раз выросло
  const sizeMult = sizes.length >= 2 && sizes[0] ? Math.round(sizes[sizes.length - 1] / sizes[0]) : null;
  const good = pOpt == null ? growth <= 0.2 : growth - pOpt <= 0.2; // близко к оптимуму (у A он может быть не плоским)
  const color = good ? 'var(--axis-o)' : 'var(--danger)';
  const W = 560, H = 200, M = { l: 54, r: 20, t: 20, b: 42 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;
  const xmin = Math.min(...sizes), xmax = Math.max(...sizes);
  const ymax = Math.max(...series, 1);
  const sx = (v) => M.l + (xmax === xmin ? 0.5 : (v - xmin) / (xmax - xmin)) * pw;
  const sy = (v) => M.t + (1 - v / ymax) * ph;
  const line = sizes.map((s, i) => `${sx(s)},${sy(series[i])}`).join(' ');
  return (
    <div style={{ padding: 16 }}>
      <div style={{ fontSize: 14.5, fontWeight: 600, color, marginBottom: 5 }}>
        {good
          ? (isB ? 'Оптимально: берёт данные набором' : 'Оптимальный класс роста')
          : (isB ? 'Запрос в цикле — тормозит на объёме' : 'Неоптимально — число операций растёт слишком быстро')}
      </div>
      <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--ink-300)', lineHeight: 1.5, maxWidth: '60ch' }}>
        {good
          ? (isB
            ? `Сколько бы данных ни было, число ${unit} почти не меняется — решение обрабатывает всё разом. На большой базе останется быстрым.`
            : `Число ${unit} растёт не быстрее, чем нужно для этой задачи. На больших входах решение останется быстрым.`)
          : (isB
            ? `С ростом (${xlabel}) число ${unit} растёт почти пропорционально — на большой базе решение будет тормозить.`
            : `Число ${unit} растёт быстрее оптимума — на больших входах решение будет медленным.`)}
      </p>
      <div style={{ overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', minWidth: 380, maxWidth: W, height: 'auto', display: 'block' }}>
          <line x1={M.l} y1={M.t} x2={M.l} y2={M.t + ph} stroke="var(--line)" strokeWidth="1" />
          <line x1={M.l} y1={M.t + ph} x2={M.l + pw} y2={M.t + ph} stroke="var(--line)" strokeWidth="1" />
          <polyline points={line} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />
          {sizes.map((s, i) => (
            <g key={i}>
              <circle cx={sx(s)} cy={sy(series[i])} r="4.5" fill={color} stroke="var(--surface)" strokeWidth="1.5" />
              <text x={sx(s)} y={sy(series[i]) - 11} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="11" fontWeight="700" fill="var(--ink-100)">{series[i]}</text>
              <text x={sx(s)} y={M.t + ph + 18} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="10.5" fill="var(--ink-400)">{s}</text>
            </g>
          ))}
          <text x={M.l + pw / 2} y={H - 5} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="10.5" fill="var(--ink-400)">{xlabel} →</text>
          <text x={14} y={M.t + ph / 2} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="10.5" fill="var(--ink-400)" transform={`rotate(-90 14 ${M.t + ph / 2})`}>{unit} →</text>
        </svg>
      </div>
      <div style={{ marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)' }}>
        класс роста: <span style={{ color, fontWeight: 700 }}>{growthF}</span>{pOptF != null ? <> · оптимум <span style={{ fontWeight: 700 }}>{pOptF}</span></> : ''} · чем ближе к горизонтали — тем лучше
      </div>
      <p style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--ink-400)', lineHeight: 1.6, maxWidth: '64ch' }}>
        <b style={{ color: 'var(--ink-300)' }}>Откуда числа.</b>{' '}
        {isB
          ? <><b style={{ color: 'var(--ink-300)' }}>По горизонтали</b> — размеры синтетической базы ({sizes.join(' → ')} записей), мы её постепенно наращиваем. <b style={{ color: 'var(--ink-300)' }}>Числа над точками</b> — сколько раз код сходил в СУБД на каждом размере. {sizeMult != null && grow != null ? <>База выросла в {sizeMult}× — {good ? <>обращения почти не изменились (<b style={{ color: 'var(--ink-300)' }}>{series[0]} → {series[series.length - 1]}</b>): данные берутся одним запросом.</> : <>обращения выросли примерно так же (<b style={{ color: 'var(--ink-300)' }}>{series[0]} → {series[series.length - 1]}</b>): запрос выполняется внутри цикла по записям.</>}</> : null}</>
          : <><b style={{ color: 'var(--ink-300)' }}>По горизонтали</b> — размеры входа, на которых прогнали код ({sizes.join(' → ')}, каждый вдвое больше предыдущего). <b style={{ color: 'var(--ink-300)' }}>Числа над точками</b> — сколько операций код выполнил на каждом входе (замер codestat OneScript). {sizeMult != null && grow != null ? <>Вход вырос в {sizeMult}×, операции — в {grow.toFixed(1).replace(/\.0$/, '')}×. Степень показывает, как быстро операции догоняют вход: <span style={{ fontFamily: 'var(--font-mono)' }}>N⁰</span> — не растут, <span style={{ fontFamily: 'var(--font-mono)' }}>N¹</span> — вровень (линейно), <span style={{ fontFamily: 'var(--font-mono)' }}>N²</span> — квадратично. Здесь <span style={{ color, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{growthF}</span>.</> : null}</>}
      </p>
    </div>
  );
}

function CodePane({ task, info = {} }) {
  const [tab, setTab] = React.useState('code');
  const [focus, setFocus] = React.useState(null); // строка, к которой прокрутить по клику на ошибку
  const goToLine = (n) => { setTab('code'); setFocus((f) => ({ line: n, seq: (f?.seq || 0) + 1 })); };
  if (!task) return null;
  const d = task.diag || {};
  const [label, color] = OUTCOME[d.outcome] || OUTCOME.unknown;
  const tests = d.tests || {};
  const gm = task.meta || {};

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      {/* шапка задачи */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', borderBottom: '1px solid var(--line)', flexWrap: 'wrap' }}>
        <Tag color={task.category === 'B' ? 'p' : 'neutral'}>{task.taskId}</Tag>
        <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-100)' }}>{task.taskName}</span>
        <div style={{ marginLeft: 'auto' }}><ScoreVector scores={task.scores} layout="compact" axes={task.category === 'A' ? ['S', 'M', 'O'] : ['S', 'M', 'O', 'P']} /></div>
      </div>

      {/* исход + тесты + метаданные генерации — с подписями */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 24, padding: '11px 16px', borderBottom: '1px solid var(--line)', flexWrap: 'wrap' }}>
        <MetaItem label="исход">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color, fontWeight: 700 }}><span style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />{label}</span>
        </MetaItem>
        {tests.total != null && (
          <MetaItem label="скрытые тесты">
            <span style={{ color: tests.passed === tests.total ? 'var(--axis-o)' : 'var(--ink-100)', fontWeight: 700 }}>{tests.passed} / {tests.total}</span>
            <span style={{ color: 'var(--ink-400)', marginLeft: 6 }}>пройдено</span>
          </MetaItem>
        )}
        <MetaItem label="токенов">
          <span style={{ color: 'var(--ink-100)', fontWeight: 700 }}>{fmtTokens(gm.tokens)}</span>
          {gm.tokensOut ? <span style={{ color: 'var(--ink-400)', marginLeft: 6 }}>вход {fmtTokens(Math.max(0, (gm.tokens || 0) - (gm.tokensOut || 0)))} · выход {fmtTokens(gm.tokensOut)}</span> : null}
        </MetaItem>
        <MetaItem label="время"><span style={{ color: 'var(--ink-100)', fontWeight: 700 }}>{fmtTime(gm.time)}</span> <span style={{ color: 'var(--ink-400)' }}>на ответ</span></MetaItem>
        <MetaItem label="цена ответа"><span style={{ color: 'var(--ink-100)', fontWeight: 700 }}>{fmtCost(gm.cost)}</span></MetaItem>
        {task.category === 'B' && (
          <MetaItem label="контекст базы">
            {gm.contextLoaded
              ? <><span style={{ color: 'var(--axis-p)', fontWeight: 700 }}>{(gm.contextObjects || []).length} об.</span><span style={{ color: 'var(--ink-400)', marginLeft: 6 }}>подтянула модель</span></>
              : <span style={{ color: 'var(--ink-400)', fontWeight: 600 }}>не запрашивался</span>}
          </MetaItem>
        )}
      </div>

      {/* разбор оценки — по каждой оси, за что балл */}
      <ScoreBreakdown items={task.breakdown} />

      {/* трейсбек — что и где упало (детали ошибок M/P) */}
      {d.errors?.length > 0 && (
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-sunken)' }}>
          <div className="prism-eyebrow" style={{ marginBottom: 8, color: 'var(--danger)' }}>что и где упало</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {d.errors.map((e, i) => {
              const lm = String(e).match(/строка\s+(\d+)/);
              const ln = lm ? Number(lm[1]) : null;
              return (
                <div key={i} onClick={ln ? () => goToLine(ln) : undefined} title={ln ? 'показать строку в коде' : undefined}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-200)', background: 'var(--danger-soft)', borderLeft: '2px solid var(--danger)', borderRadius: '0 var(--radius-xs) var(--radius-xs) 0', padding: '7px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', cursor: ln ? 'pointer' : 'default' }}>
                  {e}{ln ? <span style={{ color: 'var(--ink-400)' }}>  → к строке {ln}</span> : null}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* вкладки: код модели · условие задачи · скрытые тесты */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '0 16px', borderBottom: '1px solid var(--line)' }}>
        <CodeTab label="Код модели" active={tab === 'code'} onClick={() => setTab('code')} />
        <CodeTab label="Условие" active={tab === 'prompt'} onClick={() => setTab('prompt')} />
        <CodeTab label="Тесты" active={tab === 'tests'} onClick={() => setTab('tests')} />
        {task.perf && <CodeTab label="Нагрузка" active={tab === 'perf'} onClick={() => setTab('perf')} />}
        {info.config && <CodeTab label="База 1С" active={tab === 'base'} onClick={() => setTab('base')} />}
      </div>

      {tab === 'perf' && task.perf && <PerfChart perf={task.perf} />}

      {tab === 'code' && (task.empty
        ? <div style={{ padding: '28px 16px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-400)' }}>модель не вернула код по этой задаче</div>
        : <CodeView html={task.codeHtml} errorLines={task.errorLines} focus={focus} />)}

      {tab === 'prompt' && (
        <div style={{ padding: '16px' }}>
          {info.signature && <pre style={{ margin: '0 0 12px', padding: '10px 12px', background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--axis-s)', overflow: 'auto' }}>{info.signature}</pre>}
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--ink-200)', whiteSpace: 'pre-wrap' }}>{info.prompt || 'условие недоступно'}</p>
        </div>
      )}

      {tab === 'tests' && (info.tests
        ? <TestCases cases={info.tests} failed={d.failedIdx || []} passed={tests.passed} total={tests.total} />
        : info.testsHtml
          ? <div className="code-pane" dangerouslySetInnerHTML={{ __html: info.testsHtml }} />
          : <div style={{ padding: '28px 16px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-400)' }}>тесты не найдены</div>)}

      {tab === 'base' && (
        <div>
          {/* что модель подтянула из синтетической базы (агентный контекст) */}
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)' }}>
            <div className="prism-eyebrow" style={{ marginBottom: 8 }}>что модель подтянула из базы</div>
            {gm.contextObjects?.length
              ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{gm.contextObjects.map((o, i) => <Tag key={i} color="p">{o}</Tag>)}</div>
              : <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>контекст пуст — модель не запрашивала метаданные базы</span>}
          </div>
          {/* объекты синтетической конфигурации 1С — карточками */}
          <ConfigView config={info.config} />
        </div>
      )}
    </div>
  );
}

// лёгкий загрузчик файла генераций модели (кэш в рамках жизни компонента)
function useGen(id) {
  const [gen, setGen] = React.useState(null);
  const [err, setErr] = React.useState(false);
  React.useEffect(() => {
    if (!id) { setGen(null); setErr(false); return; }
    let alive = true; setGen(null); setErr(false);
    fetch(`${BASE}data/gen/${id}.json`).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((g) => { if (alive) setGen(g); }).catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, [id]);
  return [gen, err];
}

// шапка колонки сравнения: какая модель + кнопка убрать
function PaneHead({ name, vendor, onClose }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
      <VendorLogo vendor={vendor} name={name} size={26} />
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--ink-100)', flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
      {onClose && <button onClick={onClose} title="убрать сравнение" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 16, lineHeight: 1, padding: 2 }}>×</button>}
    </div>
  );
}

function GenerationsBrowser({ modelId, modelName, models = [] }) {
  const isMobile = useIsMobile();
  const [info, setInfo] = React.useState({});
  const [sel, setSel] = React.useState(null);
  const [cmpId, setCmpId] = React.useState('');
  const [gen, err] = useGen(modelId);
  const [genB, errB] = useGen(cmpId || null);

  React.useEffect(() => {
    let alive = true;
    fetch(`${BASE}data/tasks.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}))
      .then((ti) => { if (alive) setInfo(ti); });
    return () => { alive = false; };
  }, []);
  React.useEffect(() => { if (gen && sel == null) setSel(gen.tasks[0]?.taskId ?? null); }, [gen]);

  if (err) return <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>генерации не найдены.</p>;
  if (!gen) return <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>загрузка генераций…</p>;

  const groups = [['A', 'категория A · алгоритмика'], ['B', 'категория B · платформа']];
  const current = gen.tasks.find((t) => t.taskId === sel);
  const currentB = genB?.tasks.find((t) => t.taskId === sel);
  const cmpModel = models.find((x) => x.id === cmpId);
  const meVendor = models.find((x) => x.id === modelId)?.vendor;
  const others = models.filter((x) => x.id !== modelId);

  const selectStyle = { background: 'var(--surface-sunken)', color: 'var(--ink-200)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', padding: '6px 10px', fontFamily: 'var(--font-mono)', fontSize: 12.5, cursor: 'pointer' };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(220px, 300px) 1fr', gap: isMobile ? 14 : 20, alignItems: 'start' }}>
      <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflowY: 'auto', overflowX: 'hidden', position: isMobile ? 'static' : 'sticky', top: 76, maxHeight: isMobile ? 280 : 'calc(100vh - 96px)' }}>
        {groups.map(([cat, label]) => {
          const items = gen.tasks.filter((t) => t.category === cat);
          if (!items.length) return null;
          return (
            <div key={cat}>
              <div className="prism-eyebrow" style={{ padding: '10px 12px 6px', borderBottom: '1px solid var(--line)', background: 'var(--surface-sunken)', position: 'sticky', top: 0, zIndex: 1 }}>{label}</div>
              {items.map((t) => <TaskItem key={t.taskId} t={t} active={t.taskId === sel} onClick={() => setSel(t.taskId)} />)}
            </div>
          );
        })}
      </div>

      <div style={{ minWidth: 0 }}>
        {/* выбор второй модели для сравнения бок-о-бок */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)' }}>сравнить с</span>
          <select value={cmpId} onChange={(e) => setCmpId(e.target.value)} style={selectStyle}>
            <option value="">— одна модель —</option>
            {others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          {cmpId && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)' }}>задача одна, код — рядом</span>}
        </div>

        {cmpId ? (
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(330px, 1fr))', gap: 16, alignItems: 'start' }}>
            <div style={{ minWidth: 0 }}>
              <PaneHead name={modelName} vendor={meVendor} />
              {current && <CodePane key={`a-${current.taskId}`} task={current} info={info[current.taskId] || {}} />}
            </div>
            <div style={{ minWidth: 0 }}>
              <PaneHead name={cmpModel?.name || '—'} vendor={cmpModel?.vendor} onClose={() => setCmpId('')} />
              {errB
                ? <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>генерации не найдены.</p>
                : !genB
                  ? <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>загрузка…</p>
                  : currentB
                    ? <CodePane key={`b-${currentB.taskId}`} task={currentB} info={info[currentB.taskId] || {}} />
                    : <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13, padding: 16 }}>нет этой задачи у модели.</p>}
            </div>
          </div>
        ) : (
          current && <CodePane key={current.taskId} task={current} info={info[current.taskId] || {}} />
        )}
      </div>
    </div>
  );
}

export function ModelDetailScreen({ modelId, models = [], meta = {}, navigate = () => {} }) {
  const m = models.find((x) => x.id === modelId);
  if (!m) return <main style={{ maxWidth: 'var(--container)', margin: '0 auto', padding: '40px 24px' }}><p>модель не найдена.</p></main>;
  const tagLabels = meta.tagLabels || {};

  return (
    <main style={{ maxWidth: 'var(--container)', margin: '0 auto', padding: '0 24px' }}>
      <div style={{ paddingTop: 28, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <Button variant="ghost" size="sm" iconLeft={<Icon name="arrowLeft" size={16} />} onClick={() => navigate('leaderboard')}>Лидерборд</Button>
        <ShareBar model={m} />
      </div>

      {/* Карточка-вердикт — она же герой страницы (имя модели здесь, в шапке не дублируем) */}
      <section style={{ margin: '18px 0 28px' }}>
        <NarrativeCard model={m} models={models} tagLabels={tagLabels} />
      </section>

      {/* Категории */}
      <section style={{ display: 'flex', gap: 18, marginBottom: 36, flexWrap: 'wrap' }}>
        <CategoryPanel title="Категория A · алгоритмика" sub="оси S · M · O" q={m.qA} scores={m.A} axisOrder={['S', 'M', 'O']} />
        <CategoryPanel title="Категория B · платформа" sub="оси S · M · O · P" q={m.qB} scores={m.B} axisOrder={['S', 'M', 'O', 'P']} />
      </section>

      {/* Браузер генераций */}
      <section style={{ paddingBottom: 8 }}>
        <h2 style={{ fontSize: 'var(--text-h3)', fontWeight: 600, color: 'var(--ink-100)', margin: '0 0 4px' }}>Что написала модель</h2>
        <p style={{ fontSize: 13, color: 'var(--ink-400)', margin: '0 0 18px' }}>Реальный код по каждой задаче — тот, что запускали против синтетической базы. Выбери задачу слева; можно поставить рядом вторую модель.</p>
        <GenerationsBrowser modelId={m.id} modelName={m.name} models={models} />
      </section>
    </main>
  );
}
