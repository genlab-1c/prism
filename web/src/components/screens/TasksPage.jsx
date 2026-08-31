/* PRISM web — страница банка задач из данных (public/data/tasks.json + tasks_meta.json
   + task_matrix.json). Первым экраном — карта прогона (задача × модель): страница
   начинается с результата, как лидерборд, а не с вводного текста.
   Ниже — сам банк: каждая задача раскрывается в условие, сигнатуру, тесты, объекты базы.
   Параметры генерации и системные промпты — внизу, справочным блоком. */
import React from 'react';
import { Icon } from '../chrome/Chrome.jsx';
import { Badge } from '../core/Badge.jsx';
import { Tag } from '../core/Tag.jsx';
import TaskHeatmap from '../prism/TaskHeatmap.jsx';

const BASE = import.meta.env.BASE_URL;

const DIFF = { easy: ['лёгкая', 'ok'], medium: ['средняя', 'warn'], hard: ['сложная', 'unproven'] };
const KIND_LABEL = {
  catalogs: 'Справочники', documents: 'Документы', accumulation_registers: 'Регистры накопления',
  information_registers: 'Регистры сведений', enums: 'Перечисления', constants: 'Константы',
};
const plural = (n, one, few, many) => {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  return b === 1 ? one : many;
};

// исходы — та же палитра, что в воронке лидерборда и на карте
const OUTCOMES = [
  ['solved', 'решено', 'var(--axis-o)'],
  ['wrong', 'неверный ответ', '#d8b13e'],
  ['runtime', 'ошибка выполнения', '#dd7a3b'],
  ['compile', 'не компилируется', 'var(--danger)'],
];

function ParamsPanel({ params = {}, prompts = {} }) {
  const [open, setOpen] = React.useState(false);
  const fmt = (v) => (Array.isArray(v) ? v.join(' / ') : v ?? '—');
  const stats = [
    ['температура', fmt(params.temperature)],
    ['прогонов', fmt(params.runs)],
    ['max_tokens', fmt(params.max_tokens)],
    ['параллельно', fmt(params.concurrency)],
  ];
  return (
    <div className="params">
      <div className="params-head">
        <dl className="params-stats">
          {stats.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
          ))}
        </dl>
        <button className="params-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          <Icon name={open ? 'arrowUp' : 'arrowDown'} size={13} />системные промпты
        </button>
      </div>
      {open && (
        <div className="params-prompts">
          {['A', 'B'].map((c) => (
            <div key={c}>
              <div className="prism-eyebrow" style={{ marginBottom: 8 }}>системный промпт · категория {c}</div>
              <pre>{prompts[c] || '—'}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConfigSummary({ config }) {
  if (!config) return null;
  const parts = [];
  for (const [k, label] of Object.entries(KIND_LABEL)) {
    const objs = config[k];
    if (objs && typeof objs === 'object' && Object.keys(objs).length) parts.push([label, Object.keys(objs)]);
  }
  if (!parts.length) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div className="prism-eyebrow" style={{ marginBottom: 6, color: 'var(--axis-p)' }}>объекты синтетической базы</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {parts.map(([label, names]) => (
          <div key={label} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)', minWidth: 130 }}>{label}</span>
            <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 5 }}>{names.map((n) => <Tag key={n} color="p">{n}</Tag>)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// сколько моделей справилось: доля решивших + полоса исходов
function SolveMeter({ stat }) {
  if (!stat || !stat.n) return null;
  const share = Math.round((stat.solved / stat.n) * 100);
  return (
    <div className="task-meter">
      <div className="cap"><b>{share}%</b><span>решили {stat.solved} из {stat.n}</span></div>
      <span className="track">
        {OUTCOMES.map(([key, label, color]) => {
          const n = stat.outcomes?.[key] || 0;
          return n ? <span key={key} title={`${label}: ${n}`} style={{ width: `${(n / stat.n) * 100}%`, background: color }} /> : null;
        })}
      </span>
    </div>
  );
}

// расшифровка полосы + чем именно кончались неудачные попытки
function FailureBreakdown({ stat, avgQ }) {
  if (!stat || !stat.n) return null;
  return (
    <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--line)' }}>
      <div className="prism-eyebrow" style={{ marginBottom: 10 }}>как справились {stat.n} моделей</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 18px', marginBottom: 12 }}>
        {OUTCOMES.map(([key, label, color]) => {
          const n = stat.outcomes?.[key] || 0;
          if (!n) return null;
          return (
            <span key={key} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-300)' }}>
              <span style={{ width: 9, height: 9, borderRadius: 2, background: color }} />
              {label} — <span style={{ color: 'var(--ink-100)', fontWeight: 600 }}>{n}</span>
            </span>
          );
        })}
        {avgQ != null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-300)' }}>
            средний балл Q — <span style={{ color: 'var(--ink-100)', fontWeight: 600 }}>{avgQ}</span>
          </span>
        )}
      </div>
      {/* «на чём спотыкались» скрыто до разбора причин: в diag.errors попадают сырые
          маркеры («PRISM_FAIL 0») и следствия вместо причин — показывать это нельзя.
          Вернуть, когда причины будут классифицироваться по metrics/error_taxonomy.yaml. */}
    </div>
  );
}

const TaskRow = React.forwardRef(function TaskRow({ t, info, stat, tagLabels = {}, open, onToggle }, ref) {
  const d = DIFF[info?.difficulty] || [info?.difficulty || '—', 'neutral'];
  const testsCount = Array.isArray(info?.tests) ? info.tests.length : null;
  const tags = [...(info?.tags?.skill || []), ...(info?.tags?.platform || [])];

  return (
    <div ref={ref} className={`task-row${open ? ' is-open' : ''}`}>
      <button className="task-head" onClick={onToggle} aria-expanded={open}>
        <span className="task-id"><Tag color={t.category === 'B' ? 'p' : 'neutral'}>{t.id}</Tag></span>
        <span className="task-title">
          <span className="task-name">{t.name}</span>
          <span className="task-facts">
            <span className={`tag is-diff diff-${info?.difficulty || 'none'}`}>{d[0]}</span>
            {testsCount != null && <span>{testsCount} {plural(testsCount, 'скрытый тест', 'скрытых теста', 'скрытых тестов')}</span>}
            {tags.map((x) => <span key={x} className="tag">{tagLabels[x] || x}</span>)}
          </span>
        </span>
        <span className="task-meter-cell"><SolveMeter stat={stat} /></span>
        <span className="task-diff"><Badge tone={d[1]} dot={false} size="sm">{d[0]}</Badge></span>
        <span className="task-chev"><Icon name={open ? 'arrowUp' : 'arrowDown'} size={15} /></span>
      </button>
      {open && info && (
        <div className="task-body">
          <div className="prism-eyebrow" style={{ marginBottom: 8 }}>условие — ровно то, что видит модель</div>
          {info.signature && <pre className="task-sig">{info.signature}</pre>}
          <p className="task-prompt">{info.prompt || 'условие недоступно'}</p>
          <ConfigSummary config={info.config} />
          <FailureBreakdown stat={stat} avgQ={stat?.avg?.Q} />
        </div>
      )}
    </div>
  );
});

export default function TasksPage() {
  const [info, setInfo] = React.useState(null);
  const [meta, setMeta] = React.useState(null);
  const [matrix, setMatrix] = React.useState(null);
  const [err, setErr] = React.useState(false);
  const [openId, setOpenId] = React.useState(null);
  const rowRefs = React.useRef({});

  React.useEffect(() => {
    let alive = true;
    Promise.all([
      fetch(`${BASE}data/tasks.json`).then((r) => (r.ok ? r.json() : Promise.reject())),
      fetch(`${BASE}data/tasks_meta.json`).then((r) => (r.ok ? r.json() : Promise.reject())),
      fetch(`${BASE}data/task_matrix.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([i, m, x]) => { if (alive) { setInfo(i); setMeta(m); setMatrix(x); } }).catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, []);

  // клик по карте — раскрыть задачу в списке и подвести к ней (отдельных страниц задач пока нет)
  const openTask = React.useCallback((id) => {
    setOpenId(id);
    requestAnimationFrame(() => rowRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  }, []);

  const stats = React.useMemo(() => Object.fromEntries((matrix?.tasks || []).map((t) => [t.id, t])), [matrix]);

  const wrap = { maxWidth: 'var(--container)', margin: '0 auto', padding: '0 24px' };
  if (err) return <main style={wrap}><p style={{ padding: '40px 0', color: 'var(--ink-400)', fontFamily: 'var(--font-mono)' }}>данные задач не найдены.</p></main>;
  if (!info || !meta) return <main style={wrap}><p style={{ padding: '40px 0', color: 'var(--ink-400)', fontFamily: 'var(--font-mono)' }}>загрузка…</p></main>;

  const groups = [['A', 'Категория A · алгоритмика'], ['B', 'Категория B · платформа 1С']];

  return (
    <main style={{ ...wrap, paddingTop: 24, paddingBottom: 60 }}>
      {matrix && <TaskHeatmap data={matrix} onOpenTask={openTask} />}

      {groups.map(([cat, label]) => {
        const list = meta.order.filter((t) => t.category === cat);
        if (!list.length) return null;
        return (
          <section key={cat} style={{ marginBottom: 32 }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 16, fontWeight: 600, color: 'var(--ink-100)' }}>{label}</h2>
            {list.map((t) => (
              <TaskRow key={t.id} t={t} info={info[t.id]} stat={stats[t.id]} tagLabels={matrix?.tagLabels || {}}
                ref={(el) => { rowRefs.current[t.id] = el; }}
                open={openId === t.id}
                onToggle={() => setOpenId((cur) => (cur === t.id ? null : t.id))} />
            ))}
          </section>
        );
      })}

      <ParamsPanel params={meta.params} prompts={meta.prompts} />
    </main>
  );
}
