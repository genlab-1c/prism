/* PRISM web — экран лидерборда. Все виды README, спроектированные по дизайн-системе.
   Вкладки: Сводка · Категория A · Категория B; в A/B — Баллы · Где ломается · Профиль.
   Виды собраны из примитивов DS (RankBadge, QScore, Badge, Tag) — не транскрипция таблиц. */
import React from 'react';
import { Icon } from '../chrome/Chrome.jsx';
import { Avatar } from '../core/Avatar.jsx';
import { Badge } from '../core/Badge.jsx';
import { Tag } from '../core/Tag.jsx';
import { RankBadge } from '../prism/RankBadge.jsx';
import { VendorLogo } from '../prism/VendorLogo.jsx';
import { EconomyView } from './Economy.jsx';
import { LeaderChart, TableExport, SummaryTableSvg, ScoresTableSvg } from '../prism/LeaderChart.jsx';
import { useIsMobile } from '../../lib/useMediaQuery.js';

// закреплённая слева колонка (имя модели остаётся видимым при горизонтальной прокрутке)
const stickyLeft = (bg) => ({ position: 'sticky', left: 0, zIndex: 1, background: bg });

const AXIS_COLOR = { S: 'var(--axis-s)', M: 'var(--axis-m)', O: 'var(--axis-o)', P: 'var(--axis-p)' };
// исходы воронки: цвет на каждый, от лучшего к худшему
const BUCKETS = [
  ['решено', 'var(--axis-o)'],
  ['неверный ответ', '#d8b13e'],
  ['ошибка выполнения', '#dd7a3b'],
  ['не компилируется', 'var(--danger)'],
];

/* ===================== общие примитивы ===================== */
function Shield({ label, value, tone = 'neutral', icon }) {
  const tones = { neutral: 'var(--ink-200)', ok: 'var(--ok)', brand: 'var(--brand)', s: 'var(--axis-s)' };
  return (
    <span style={{ display: 'inline-flex', alignItems: 'stretch', borderRadius: 'var(--radius-xs)', overflow: 'hidden', border: '1px solid var(--line)', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1, height: 20 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '0 7px', background: 'var(--surface-sunken)', color: 'var(--ink-400)' }}>{icon && <Icon name={icon} size={11} />}{label}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', padding: '0 7px', background: 'var(--surface-raised)', color: tones[tone] || tones.neutral, fontWeight: 600 }}>{value}</span>
    </span>
  );
}

// быстрый старт: git clone + раскрывающийся список команд (как в README)
const QUICK_CMDS = [
  ['cd prism && make setup-all', 'окружение (uv) + инструменты осей + учебная 1С'],
  ['uv run prism leaderboard', 'лидерборд из готовых оценок (мгновенно)'],
  ['uv run prism generate --category A --models claude', 'генерация одной моделью'],
  ['uv run prism score', 'исполнить код и пересчитать оценки L1'],
  ['uv run prism doctor', 'проверить окружение, инструменты, ключи'],
];
function CmdLine({ cmd, hint, primary }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: primary ? '11px 14px' : '8px 14px', borderTop: primary ? 'none' : '1px solid var(--line)' }}>
      <div style={{ minWidth: 0 }}>
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: primary ? 13 : 12.5, color: 'var(--ink-100)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', display: 'block' }}>
          <span style={{ color: 'var(--axis-o)', userSelect: 'none' }}>$ </span>{cmd}
        </code>
        {hint && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--ink-400)' }}>{hint}</span>}
      </div>
      <button onClick={() => { try { navigator.clipboard.writeText(cmd); } catch (e) {} setCopied(true); setTimeout(() => setCopied(false), 1200); }}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', color: copied ? 'var(--ok)' : 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 11.5, flex: 'none' }}>
        <Icon name={copied ? 'check' : 'copy'} size={14} />{copied ? 'ок' : 'copy'}
      </button>
    </div>
  );
}
function QuickStart({ repo }) {
  const [open, setOpen] = React.useState(false);
  const clone = `git clone ${repo?.url || 'https://github.com/genlab-1c/prism'}`;
  return (
    <div style={{ background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
      <CmdLine cmd={clone} primary />
      {open && QUICK_CMDS.map(([cmd, hint]) => <CmdLine key={cmd} cmd={cmd} hint={hint} />)}
      <button onClick={() => setOpen((v) => !v)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, background: 'var(--surface)', border: 'none', borderTop: '1px solid var(--line)', cursor: 'pointer', color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 11.5, padding: '7px' }}>
        <Icon name={open ? 'arrowUp' : 'arrowDown'} size={13} />{open ? 'свернуть' : 'команды бенчмарка'}
      </button>
    </div>
  );
}

function Tab({ label, sub, active, onClick }) {
  return (
    <button onClick={onClick} style={{ background: 'none', border: 'none', borderBottom: `2px solid ${active ? 'var(--brand)' : 'transparent'}`, cursor: 'pointer', padding: '0 2px 12px', display: 'flex', flexDirection: 'column', gap: 2, textAlign: 'left', marginBottom: -1 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13.5, fontWeight: 600, color: active ? 'var(--ink-100)' : 'var(--ink-400)' }}>{label}</span>
      {sub && <span style={{ fontSize: 11.5, color: 'var(--ink-400)' }}>{sub}</span>}
    </button>
  );
}

function Segmented({ items, value, onChange }) {
  return (
    <div style={{ display: 'inline-flex', gap: 2, padding: 3, background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)' }}>
      {items.map((it) => {
        const on = it.key === value;
        return <button key={it.key} onClick={() => onChange(it.key)} style={{ border: 'none', cursor: 'pointer', borderRadius: 'var(--radius-sm)', padding: '7px 15px', fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: on ? 600 : 500, background: on ? 'var(--surface-raised)' : 'transparent', color: on ? 'var(--ink-100)' : 'var(--ink-400)', transition: 'background var(--dur-fast) var(--ease)' }}>{it.label}</button>;
      })}
    </div>
  );
}

function Identity({ m, size = 38 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>
      <VendorLogo vendor={m.vendor} name={m.name} size={size} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, color: 'var(--ink-100)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.name}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)', marginTop: 1 }}>{m.family}</div>
      </div>
    </div>
  );
}

const card = { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)' };
// скруглённая шапка таблицы (без sticky — иначе ломается внутри горизонтального скролла)
const headStick = { borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0' };
// обёртка плотной таблицы: на узких экранах едет горизонтально, не ломая страницу
function TableScroll({ minWidth = 640, children }) {
  return (
    <div style={{ ...card, overflowX: 'auto' }}>
      <div style={{ minWidth }}>{children}</div>
    </div>
  );
}
function ListRow({ grid, i, top, onClick, children }) {
  const [h, setH] = React.useState(false);
  return (
    <div role="button" tabIndex={0} onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)} onClick={onClick}
      style={{ display: 'grid', gridTemplateColumns: grid, gap: 18, alignItems: 'center', padding: '14px 20px', cursor: 'pointer',
        borderTop: i ? '1px solid var(--line)' : 'none',
        background: h ? 'var(--surface-raised)' : (top ? 'var(--top-tint)' : 'transparent'),
        boxShadow: top && !h ? 'inset 2px 0 0 var(--brand)' : 'none',
        transition: 'background var(--dur) var(--ease)' }}>{children}</div>
  );
}
const colHead = (extra = {}) => ({ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-400)', ...extra });

/* ===================== вид: Баллы (overall, плотная сортируемая таблица) ===================== */
function SortHead({ label, axis, sortKey, dir, onSort }) {
  const active = sortKey === axis;
  return (
    <button onClick={() => onSort(axis)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'inline-flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end', width: '100%', ...colHead(), color: active ? (AXIS_COLOR[axis] || 'var(--ink-100)') : 'var(--ink-400)' }}>
      {label}<Icon name={active ? (dir === 'desc' ? 'arrowDown' : 'arrowUp') : 'arrowUpDown'} size={12} style={{ opacity: active ? 1 : 0.5 }} />
    </button>
  );
}
function ScoreCell({ v, axis }) {
  const has = v != null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 5 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 14, fontWeight: 600, color: has ? 'var(--ink-100)' : 'var(--ink-400)' }}>{has ? v.toFixed(1) : '—'}</span>
      <div style={{ width: 38, height: 3, borderRadius: 2, background: 'var(--track-bg)', overflow: 'hidden' }}>{has && <div style={{ width: `${(v / 10) * 100}%`, height: '100%', background: AXIS_COLOR[axis] }} />}</div>
    </div>
  );
}
function OverallTable({ cat, models, navigate }) {
  const axes = cat === 'A' ? ['S', 'M', 'O'] : ['S', 'M', 'O', 'P'];
  const grid = cat === 'A' ? '34px minmax(170px,1fr) 52px 52px 52px 64px 50px 78px' : '34px minmax(160px,1fr) 48px 48px 48px 48px 60px 50px 76px';
  const [sortKey, setSortKey] = React.useState('q');
  const [dir, setDir] = React.useState('desc');
  const onSort = (k) => { if (k === sortKey) setDir((d) => (d === 'desc' ? 'asc' : 'desc')); else { setSortKey(k); setDir('desc'); } };
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const qRank = {};
  [...models].filter((m) => m[qKey] != null).sort((a, b) => b[qKey] - a[qKey]).forEach((m, i) => { qRank[m.id] = i + 1; });
  const rows = models.filter((m) => m[qKey] != null && m[cat]).sort((a, b) => {
    const av = sortKey === 'q' ? a[qKey] : (a[cat][sortKey] ?? -1);
    const bv = sortKey === 'q' ? b[qKey] : (b[cat][sortKey] ?? -1);
    return dir === 'desc' ? bv - av : av - bv;
  });
  return (
    <TableScroll minWidth={cat === 'A' ? 680 : 720}>
      <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 14, alignItems: 'center', padding: '0 20px', height: 40, background: 'var(--surface-sunken)', borderBottom: '1px solid var(--line)', ...headStick }}>
        <span style={colHead()}>#</span><span style={colHead()}>модель</span>
        {axes.map((a) => <SortHead key={a} label={a} axis={a} sortKey={sortKey} dir={dir} onSort={onSort} />)}
        <SortHead label="Q" axis="q" sortKey={sortKey} dir={dir} onSort={onSort} />
        <span style={colHead({ textAlign: 'right' })}>±</span><span style={colHead({ textAlign: 'right' })}>цена</span>
      </div>
      {rows.map((m) => {
        const r = qRank[m.id];
        return (
          <div key={m.id} onClick={() => navigate('model', m.id)}
            style={{ display: 'grid', gridTemplateColumns: grid, gap: 14, alignItems: 'center', padding: '0 20px', height: 56, borderTop: '1px solid var(--line)', cursor: 'pointer', background: r === 1 ? 'var(--top-tint)' : 'transparent' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-raised)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = r === 1 ? 'var(--top-tint)' : 'transparent')}>
            <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 13, fontWeight: 700, color: r === 1 ? 'var(--brand)' : 'var(--ink-400)' }}>{r}</span>
            <Identity m={m} size={30} />
            {axes.map((a) => <ScoreCell key={a} v={m[cat][a]} axis={a} />)}
            <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 17, fontWeight: 700, color: 'var(--ink-100)' }}>{m[qKey].toFixed(2)}</span>
            <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)' }}>{m[cat].margin != null ? `±${m[cat].margin.toFixed(1)}` : '—'}</span>
            <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)' }}>{m.cost}</span>
          </div>
        );
      })}
    </TableScroll>
  );
}

/* ===================== вид: Сводка ===================== */
// доля решённых: цвет по уровню — мгновенно виден разрыв A/B
const solvedColor = (s) => (s == null ? 'var(--ink-400)' : s >= 0.7 ? 'var(--axis-o)' : s >= 0.4 ? 'var(--warn)' : 'var(--danger)');

function SolvedStat({ solved }) {
  if (solved == null) return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>не измерялось</span>;
  const pct = Math.round(solved * 100);
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 3 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 25, fontWeight: 700, letterSpacing: '-0.01em', lineHeight: 1, color: solvedColor(solved) }}>{pct}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: solvedColor(solved), opacity: 0.7 }}>%</span>
      <span style={{ marginLeft: 8, fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.04em', color: 'var(--ink-400)' }}>решено</span>
    </div>
  );
}
function SummaryView({ models, navigate }) {
  const overall = (m) => { const v = [m.A?.solved, m.B?.solved].filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : -1; };
  const rows = [...models].sort((a, b) => overall(b) - overall(a));
  const grid = '44px minmax(180px,1.4fr) minmax(150px,1fr) minmax(150px,1fr)';
  return (
    <TableScroll minWidth={620}>
      <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 18, alignItems: 'center', padding: '0 20px', height: 40, background: 'var(--surface-sunken)', borderBottom: '1px solid var(--line)', ...headStick }}>
        <span style={colHead()}>#</span><span style={colHead()}>модель</span>
        <span style={colHead()}>алгоритмика · A</span><span style={colHead()}>платформа 1С · B</span>
      </div>
      {rows.map((m, i) => (
        <ListRow key={m.id} grid={grid} i={i} top={i === 0} onClick={() => navigate('model', m.id)}>
          <RankBadge rank={i + 1} />
          <Identity m={m} />
          <SolvedStat solved={m.A?.solved} />
          <SolvedStat solved={m.B?.solved} />
        </ListRow>
      ))}
    </TableScroll>
  );
}

/* ===================== вид: Где ломается (воронка) ===================== */
function OutcomeBar({ f }) {
  if (!f?.n) return null;
  return (
    <div style={{ display: 'flex', width: '100%', height: 16, borderRadius: 'var(--radius-pill)', overflow: 'hidden', background: 'var(--track-bg)', border: '1px solid var(--line)' }}>
      {BUCKETS.map(([k, c]) => { const w = (f.buckets[k] || 0) / f.n * 100; return w ? <div key={k} title={`${k}: ${f.buckets[k]} из ${f.n}`} style={{ width: `${w}%`, background: c }} /> : null; })}
    </div>
  );
}
function FunnelView({ cat, models, navigate }) {
  const rows = models.filter((m) => m[cat]?.funnel?.n).sort((a, b) => (b[cat].solved ?? -1) - (a[cat].solved ?? -1));
  const grid = '44px minmax(150px,1fr) 66px minmax(200px,1.5fr) minmax(140px,0.9fr)';
  return (
    <>
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 14 }}>
        {BUCKETS.map(([k, c]) => <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-300)' }}><span style={{ width: 9, height: 9, borderRadius: 3, background: c }} />{k}</span>)}
      </div>
      <TableScroll minWidth={680}>
        <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 18, alignItems: 'center', padding: '0 20px', height: 40, background: 'var(--surface-sunken)', borderBottom: '1px solid var(--line)', ...headStick }}>
          <span style={colHead()}>#</span><span style={colHead()}>модель</span><span style={colHead({ textAlign: 'right' })}>решено</span><span style={colHead()}>исход всех попыток</span><span style={colHead()}>частая поломка</span>
        </div>
        {rows.map((m, i) => {
          const f = m[cat].funnel;
          const pct = Math.round((m[cat].solved || 0) * 100);
          return (
            <ListRow key={m.id} grid={grid} i={i} top={i === 0} onClick={() => navigate('model', m.id)}>
              <RankBadge rank={i + 1} />
              <Identity m={m} />
              <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 19, fontWeight: 700, letterSpacing: '-0.01em', color: pct === 0 ? 'var(--ink-400)' : 'var(--ink-100)' }}>{pct}%</span>
              <OutcomeBar f={f} />
              <div>{f.cause ? <Badge tone={pct === 0 ? 'unproven' : 'neutral'} dot={false} size="sm" style={{ maxWidth: '100%' }}><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.cause[0]} ×{f.cause[1]}</span></Badge> : <span style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>—</span>}</div>
            </ListRow>
          );
        })}
      </TableScroll>
    </>
  );
}

/* ===================== вид: Профиль (непрерывная теплокарта) ===================== */
function ProfileView({ cat, models, cols, labels, navigate }) {
  const isMobile = useIsMobile();
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const axis = cat === 'A' ? 'm' : 'p';
  const rows = models.filter((m) => m[qKey] != null && m[cat]?.profile).sort((a, b) => b[qKey] - a[qKey]);
  if (!cols.length) return <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>нет тегов с достаточным числом задач.</p>;
  const grid = `${isMobile ? '128px' : 'minmax(180px,1.4fr)'} ${cols.map(() => (isMobile ? '64px' : 'minmax(64px,1fr)')).join(' ')}`;
  const heat = (v) => v == null
    ? { background: 'transparent', color: 'var(--ink-400)' }
    : { background: `color-mix(in srgb, var(--axis-${axis}) ${Math.round(10 + (v / 10) * 36)}%, transparent)`, color: v >= 4 ? 'var(--ink-100)' : 'var(--ink-300)' };
  return (
    <>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)', margin: '0 0 14px' }}>
        срез <span style={{ color: AXIS_COLOR[cat === 'A' ? 'M' : 'P'], fontWeight: 600 }}>{cat === 'A' ? 'M̄ — семантика по навыкам' : 'P̄ — платформа по конструкциям 1С'}</span> · насыщенность ∝ баллу · сравнивать модели внутри столбца
      </p>
      <div style={{ ...card, overflowX: 'auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: grid, alignItems: 'center', background: 'var(--surface-sunken)', borderBottom: '1px solid var(--line)' }}>
          <span style={{ ...colHead(), padding: '12px 20px', ...stickyLeft('var(--surface-sunken)'), zIndex: 2 }}>модель</span>
          {cols.map((c) => <span key={c} style={{ padding: '10px 6px', display: 'grid', placeItems: 'center' }}><Tag color={cat === 'A' ? 'm' : 'p'}>{labels[c] || c}</Tag></span>)}
        </div>
        {rows.map((m, i) => (
          <div key={m.id} onClick={() => navigate('model', m.id)}
            style={{ display: 'grid', gridTemplateColumns: grid, alignItems: 'stretch', borderTop: '1px solid var(--line)', cursor: 'pointer', background: i === 0 ? 'var(--top-tint)' : 'transparent' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--hover-overlay)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = i === 0 ? 'var(--top-tint)' : 'transparent')}>
            <div style={{ padding: '10px 20px', ...stickyLeft(i === 0 ? 'var(--top-tint)' : 'var(--surface)') }}><Identity m={m} size={30} /></div>
            {cols.map((c) => {
              const v = m[cat].profile[c]?.value;
              const st = heat(v);
              return <span key={c} style={{ margin: 5, borderRadius: 'var(--radius-sm)', display: 'grid', placeItems: 'center', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 14, fontWeight: 600, ...st }}>{v != null ? v.toFixed(1) : '—'}</span>;
            })}
          </div>
        ))}
      </div>
    </>
  );
}

/* ===================== экран ===================== */
export function LeaderboardScreen({ navigate = () => {}, models = [], meta = {} }) {
  const [view, setView] = React.useState('summary');
  const [sub, setSub] = React.useState('overall');
  const [sumScope, setSumScope] = React.useState('top10'); // охват сводки: видимая таблица + картинка
  const [scoreScope, setScoreScope] = React.useState('top10'); // охват таблицы баллов A/B
  const cols = meta.profileCols || { A: [], B: [] };
  const labels = meta.tagLabels || {};
  const totalTasks = (meta.tasksA || 0) + (meta.tasksB || 0);
  const SUBS = [{ key: 'overall', label: 'Баллы' }, { key: 'funnel', label: 'Где ломается' }, { key: 'profile', label: 'Профиль' }, { key: 'charts', label: 'График' }];

  // сводка: сортировка по средней доле решённых A/B, срез по охвату
  const sumOverall = (m) => { const v = [m.A?.solved, m.B?.solved].filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : -1; };
  const sumRanked = React.useMemo(() => [...models].sort((a, b) => sumOverall(b) - sumOverall(a)), [models]);
  const sumShown = sumScope === 'all' ? sumRanked : sumRanked.slice(0, 10);
  // баллы A/B: сортировка по Q, срез по охвату
  const qKey = view === 'A' ? 'qA' : 'qB';
  const scoreRanked = React.useMemo(() => models.filter((m) => m[qKey] != null && m[view]).sort((a, b) => b[qKey] - a[qKey]), [models, qKey, view]);
  const scoreShown = scoreScope === 'all' ? scoreRanked : scoreRanked.slice(0, 10);

  return (
    <main style={{ maxWidth: 'var(--container)', margin: '0 auto', padding: '0 24px' }}>
      <section style={{ paddingTop: 40, paddingBottom: 24 }}>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 600, color: 'var(--ink-100)', letterSpacing: '-0.01em' }}>
          prism <span style={{ color: 'var(--ink-400)', fontWeight: 400 }}>— многомерная оценка генерации кода 1С</span>
        </h1>
        <p style={{ margin: '12px 0 0', fontSize: 14.5, color: 'var(--ink-300)', maxWidth: 680, lineHeight: 1.6 }}>
          Открытый бенчмарк качества генерации кода 1С. Код, который написала модель, мы <span style={{ color: 'var(--ink-100)' }}>по-настоящему исполняем</span> — компилятор, скрытые тесты, живая база&nbsp;1С — и оцениваем по четырём осям&nbsp;<span style={{ color: 'var(--axis-s)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>S</span> <span style={{ color: 'var(--axis-m)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>M</span> <span style={{ color: 'var(--axis-o)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>O</span> <span style={{ color: 'var(--axis-p)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>P</span> (синтаксис · смысл · оптимальность · платформа), а не по принципу «прошло&nbsp;/ не&nbsp;прошло».
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 16, alignItems: 'center' }}>
          <Shield label="версия" value={`v${meta.version || '—'}`} tone="brand" />
          <Shield label="лицензия" value="MIT" />
          <Shield label="задач" value={String(totalTasks)} />
          <Shield label="тест-кейсов" value={String(meta.cases || '—')} />
          <Shield label="генераций" value={String(meta.gens || '—')} />
          <Shield label="моделей" value={String(meta.models || models.length)} />
          <Shield label="обновлено" value={meta.lastRun || '—'} tone="ok" />
          <Shield label="уровень" value="L1 · машина" tone="s" icon="cpu" />
        </div>
        <div style={{ marginTop: 16, maxWidth: 520 }}><QuickStart repo={meta.repo} /></div>
        <p style={{ margin: '14px 0 0', fontSize: 13.5, color: 'var(--ink-300)', maxWidth: 680, lineHeight: 1.55 }}>
          Участвуйте: добавьте свою модель в лидерборд или пришлите готовый прогон.{' '}
          <a href={(meta.repo?.url || 'https://github.com/genlab-1c/prism')} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--brand)', textDecoration: 'none', fontWeight: 600 }}>Как поучаствовать</a>
        </p>
      </section>

      <div style={{ display: 'flex', gap: 28, borderBottom: '1px solid var(--line)', marginBottom: 24 }}>
        <Tab label="Сводка" sub="кто лучше в целом" active={view === 'summary'} onClick={() => setView('summary')} />
        <Tab label="Категория A" sub="алгоритмика · OneScript" active={view === 'A'} onClick={() => setView('A')} />
        <Tab label="Категория B" sub="платформа · реальная 1С" active={view === 'B'} onClick={() => setView('B')} />
        <Tab label="Экономика" sub="качество ↔ цена" active={view === 'econ'} onClick={() => setView('econ')} />
      </div>

      {view === 'econ' && <EconomyView models={models} navigate={navigate} />}

      {view === 'summary' && (
        <>
          <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-400)', lineHeight: 1.5 }}>Модели отсортированы по доле решённых задач в категориях A и B. «Решено» — код прошёл все скрытые проверки.</p>
          <TableExport scope={sumScope} setScope={setSumScope} count={sumRanked.length} name={`prism_summary_${sumScope}`}
            render={(ref, C) => <SummaryTableSvg svgRef={ref} rows={sumShown} meta={meta} C={C} />} />
          <SummaryView models={sumShown} navigate={navigate} />
        </>
      )}

      {(view === 'A' || view === 'B') && (
        <>
          <div style={{ marginBottom: 16 }}><Segmented items={SUBS} value={sub} onChange={setSub} /></div>
          {sub === 'overall' && <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-400)', lineHeight: 1.5 }}>{view === 'A' ? `${meta.tasksA || 0} алгоритмических задач` : `${meta.tasksB || 0} платформенных задач`}. Q — средний балл по осям. ± — погрешность оценки (95% доверительный интервал).</p>}
          {sub === 'overall' && <TableExport scope={scoreScope} setScope={setScoreScope} count={scoreRanked.length} name={`prism_scores_${view}_${scoreScope}`}
            render={(ref, C) => <ScoresTableSvg svgRef={ref} cat={view} rows={scoreShown} meta={meta} C={C} />} />}
          {sub === 'overall' && <OverallTable cat={view} models={scoreShown} navigate={navigate} />}
          {sub === 'funnel' && <FunnelView cat={view} models={models} navigate={navigate} />}
          {sub === 'profile' && <ProfileView cat={view} models={models} cols={cols[view]} labels={labels} navigate={navigate} />}
          {sub === 'charts' && <LeaderChart key={view} cat={view} models={models} meta={meta} navigate={navigate} />}
        </>
      )}
    </main>
  );
}
