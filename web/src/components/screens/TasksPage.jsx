/* PRISM web — страница банка задач из данных (public/data/tasks.json + tasks_meta.json),
   а не из docs. Показывает: как мы запускаем модели (параметры генерации + системные
   промпты) и сам банк — каждая задача раскрывается в условие, сигнатуру, тесты, объекты базы. */
import React from 'react';
import { Icon } from '../chrome/Chrome.jsx';
import { Badge } from '../core/Badge.jsx';
import { Tag } from '../core/Tag.jsx';

const BASE = import.meta.env.BASE_URL;

const DIFF = { easy: ['лёгкая', 'ok'], medium: ['средняя', 'warn'], hard: ['сложная', 'unproven'] };
const KIND_LABEL = {
  catalogs: 'Справочники', documents: 'Документы', accumulation_registers: 'Регистры накопления',
  information_registers: 'Регистры сведений', enums: 'Перечисления', constants: 'Константы',
};

function ParamsPanel({ params = {}, prompts = {} }) {
  const [open, setOpen] = React.useState(false);
  const stat = (label, value) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 700, color: 'var(--ink-100)' }}>{value}</span>
    </div>
  );
  const fmt = (v) => (Array.isArray(v) ? v.join(' / ') : v ?? '—');
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', marginBottom: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, padding: '16px 20px' }}>
        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
          {stat('температура', fmt(params.temperature))}
          {stat('прогонов', fmt(params.runs))}
          {stat('max_tokens', fmt(params.max_tokens))}
          {stat('параллельно', fmt(params.concurrency))}
        </div>
        <button onClick={() => setOpen((v) => !v)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', cursor: 'pointer', color: 'var(--ink-200)', fontFamily: 'var(--font-mono)', fontSize: 12, padding: '7px 12px' }}>
          <Icon name={open ? 'arrowUp' : 'arrowDown'} size={13} />системные промпты
        </button>
      </div>
      {open && (
        <div style={{ borderTop: '1px solid var(--line)', padding: '16px 20px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
          {['A', 'B'].map((c) => (
            <div key={c}>
              <div className="prism-eyebrow" style={{ marginBottom: 8 }}>системный промпт · категория {c}</div>
              <pre style={{ margin: 0, padding: '12px 14px', background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-200)', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{prompts[c] || '—'}</pre>
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

function TaskRow({ t, info }) {
  const [open, setOpen] = React.useState(false);
  const d = DIFF[info?.difficulty] || [info?.difficulty || '—', 'neutral'];
  const testsCount = Array.isArray(info?.tests) ? info.tests.length : null;
  return (
    <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', marginBottom: 8, overflow: 'hidden', background: 'var(--surface)' }}>
      <button onClick={() => setOpen((v) => !v)} style={{ width: '100%', display: 'grid', gridTemplateColumns: '46px 1fr auto auto', gap: 12, alignItems: 'center', padding: '12px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
        <Tag color={t.category === 'B' ? 'p' : 'neutral'}>{t.id}</Tag>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-100)' }}>{t.name}</span>
        <Badge tone={d[1]} dot={false} size="sm">{d[0]}</Badge>
        <Icon name={open ? 'arrowUp' : 'arrowDown'} size={15} style={{ color: 'var(--ink-400)' }} />
      </button>
      {open && info && (
        <div style={{ borderTop: '1px solid var(--line)', padding: '16px' }}>
          {info.signature && <pre style={{ margin: '0 0 12px', padding: '10px 12px', background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--axis-s)', overflow: 'auto' }}>{info.signature}</pre>}
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--ink-200)', whiteSpace: 'pre-wrap' }}>{info.prompt || 'условие недоступно'}</p>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)' }}>
            {testsCount != null && <span>скрытых тест-кейсов: <span style={{ color: 'var(--ink-200)', fontWeight: 600 }}>{testsCount}</span></span>}
            {t.category === 'B' && info.testsHtml && <span>проверки исполняются в 1С против синтетической базы</span>}
          </div>
          <ConfigSummary config={info.config} />
        </div>
      )}
    </div>
  );
}

export default function TasksPage() {
  const [info, setInfo] = React.useState(null);
  const [meta, setMeta] = React.useState(null);
  const [err, setErr] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    Promise.all([
      fetch(`${BASE}data/tasks.json`).then((r) => (r.ok ? r.json() : Promise.reject())),
      fetch(`${BASE}data/tasks_meta.json`).then((r) => (r.ok ? r.json() : Promise.reject())),
    ]).then(([i, m]) => { if (alive) { setInfo(i); setMeta(m); } }).catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, []);

  const wrap = { maxWidth: 'var(--container)', margin: '0 auto', padding: '0 24px' };
  if (err) return <main style={wrap}><p style={{ padding: '40px 0', color: 'var(--ink-400)', fontFamily: 'var(--font-mono)' }}>данные задач не найдены.</p></main>;
  if (!info || !meta) return <main style={wrap}><p style={{ padding: '40px 0', color: 'var(--ink-400)', fontFamily: 'var(--font-mono)' }}>загрузка…</p></main>;

  const groups = [['A', 'Категория A · алгоритмика', 'чистый язык 1С, исполнение в OneScript'], ['B', 'Категория B · платформа 1С', 'реальная платформа против синтетической базы']];

  return (
    <main style={{ ...wrap, paddingBottom: 60 }}>
      <section style={{ paddingTop: 40, paddingBottom: 8 }}>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 600, color: 'var(--ink-100)' }}>Банк задач</h1>
        <p style={{ margin: '12px 0 0', fontSize: 14.5, color: 'var(--ink-300)', maxWidth: 680, lineHeight: 1.6 }}>
          Каждая задача — это <span style={{ color: 'var(--ink-100)' }}>условие, скрытые тесты и эталон</span>. Модель видит только условие; тесты скрыты, чтобы под них нельзя было подогнать ответ. Эталон обязан проходить эти тесты на 100%.
        </p>
      </section>

      <ParamsPanel params={meta.params} prompts={meta.prompts} />

      {groups.map(([cat, label, sub]) => {
        const list = meta.order.filter((t) => t.category === cat);
        if (!list.length) return null;
        return (
          <section key={cat} style={{ marginBottom: 32 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14 }}>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--ink-100)' }}>{label}</h2>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>{list.length} · {sub}</span>
            </div>
            {list.map((t) => <TaskRow key={t.id} t={t} info={info[t.id]} />)}
          </section>
        );
      })}
    </main>
  );
}
