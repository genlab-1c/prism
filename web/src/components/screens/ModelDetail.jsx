/* PRISM web — экран модели: профиль (оси A/B) + браузер генераций.
   Профиль — из DS ModelDetailScreen; «Пример задачи» заменён на настоящий
   браузер кода: список задач → реальный BSL-ответ модели (подсветка на билде).
   Код грузится лениво из public/data/gen/<id>.json по клику на модель. */
import React from 'react';
import { Icon } from '../chrome/Chrome.jsx';
import { Avatar } from '../core/Avatar.jsx';
import { Badge } from '../core/Badge.jsx';
import { Button } from '../core/Button.jsx';
import { Tag } from '../core/Tag.jsx';
import { ScoreBar } from '../prism/ScoreBar.jsx';
import { ScoreVector } from '../prism/ScoreVector.jsx';
import { QScore } from '../prism/QScore.jsx';

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
const fmtCost = (c) => (c == null ? '—' : c < 0.0005 ? '<$0.001' : `$${c.toFixed(c < 1 ? 3 : 2)}`);
const Sep = () => <span style={{ color: 'var(--line)' }}>·</span>;

function CodeTab({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '11px 4px', marginRight: 18, borderBottom: `2px solid ${active ? 'var(--brand)' : 'transparent'}`, fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: active ? 600 : 500, color: active ? 'var(--ink-100)' : 'var(--ink-400)' }}>{label}</button>
  );
}

function CodePane({ task, info = {} }) {
  const [tab, setTab] = React.useState('code');
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
        <div style={{ marginLeft: 'auto' }}><ScoreVector scores={task.scores} layout="compact" /></div>
      </div>

      {/* исход + тесты + метаданные генерации */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '9px 16px', borderBottom: '1px solid var(--line)', flexWrap: 'wrap', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color, fontWeight: 600 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />{label}
        </span>
        {tests.total != null && <span>тесты <span style={{ color: tests.passed === tests.total ? 'var(--axis-o)' : 'var(--ink-200)', fontWeight: 600 }}>{tests.passed}/{tests.total}</span></span>}
        <Sep /><span title="токенов потрачено">{fmtTokens(gm.tokens)} ток</span>
        <span title="время генерации">{fmtTime(gm.time)}</span>
        <span title="стоимость">{fmtCost(gm.cost)}</span>
        {task.category === 'B' && <><Sep /><span title="агентный сбор метаданных базы">{gm.contextLoaded ? `контекст: ${(gm.contextObjects || []).length} об.` : 'без контекста'}</span></>}
      </div>

      {/* трейсбек — наверху, сразу под исходом */}
      {d.errors?.length > 0 && (
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-sunken)' }}>
          <div className="prism-eyebrow" style={{ marginBottom: 8, color: 'var(--danger)' }}>что и где упало</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {d.errors.map((e, i) => (
              <div key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-200)', background: 'var(--danger-soft)', borderLeft: '2px solid var(--danger)', borderRadius: '0 var(--radius-xs) var(--radius-xs) 0', padding: '7px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{e}</div>
            ))}
          </div>
        </div>
      )}

      {/* вкладки: код модели · условие задачи · скрытые тесты */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '0 16px', borderBottom: '1px solid var(--line)' }}>
        <CodeTab label="Код модели" active={tab === 'code'} onClick={() => setTab('code')} />
        <CodeTab label="Условие" active={tab === 'prompt'} onClick={() => setTab('prompt')} />
        <CodeTab label="Тесты" active={tab === 'tests'} onClick={() => setTab('tests')} />
        {info.configHtml && <CodeTab label="База 1С" active={tab === 'base'} onClick={() => setTab('base')} />}
      </div>

      {tab === 'code' && (task.empty
        ? <div style={{ padding: '28px 16px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-400)' }}>модель не вернула код по этой задаче</div>
        : <div className="code-pane" dangerouslySetInnerHTML={{ __html: task.codeHtml }} />)}

      {tab === 'prompt' && (
        <div style={{ padding: '16px' }}>
          {info.signature && <pre style={{ margin: '0 0 12px', padding: '10px 12px', background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--axis-s)', overflow: 'auto' }}>{info.signature}</pre>}
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--ink-200)', whiteSpace: 'pre-wrap' }}>{info.prompt || 'условие недоступно'}</p>
        </div>
      )}

      {tab === 'tests' && (info.testsHtml
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
          {/* объекты синтетической конфигурации 1С (спека базы задачи) */}
          <div className="prism-eyebrow" style={{ padding: '12px 16px 0' }}>объекты синтетической базы 1С</div>
          <div className="code-pane" dangerouslySetInnerHTML={{ __html: info.configHtml }} />
        </div>
      )}
    </div>
  );
}

function GenerationsBrowser({ modelId }) {
  const [gen, setGen] = React.useState(null);
  const [info, setInfo] = React.useState({});
  const [sel, setSel] = React.useState(null);
  const [err, setErr] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    setGen(null); setErr(false);
    Promise.all([
      fetch(`${BASE}data/gen/${modelId}.json`).then((r) => (r.ok ? r.json() : Promise.reject())),
      fetch(`${BASE}data/tasks.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
    ])
      .then(([g, ti]) => { if (alive) { setGen(g); setInfo(ti); setSel(g.tasks[0]?.taskId ?? null); } })
      .catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, [modelId]);

  if (err) return <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>генерации не найдены.</p>;
  if (!gen) return <p style={{ color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>загрузка генераций…</p>;

  const groups = [['A', 'категория A · алгоритмика'], ['B', 'категория B · платформа 1С']];
  const current = gen.tasks.find((t) => t.taskId === sel);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 320px) 1fr', gap: 20, alignItems: 'start' }}>
      <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', position: 'sticky', top: 76 }}>
        {groups.map(([cat, label]) => {
          const items = gen.tasks.filter((t) => t.category === cat);
          if (!items.length) return null;
          return (
            <div key={cat}>
              <div className="prism-eyebrow" style={{ padding: '10px 12px 6px', borderBottom: '1px solid var(--line)', background: 'var(--surface-sunken)' }}>{label}</div>
              {items.map((t) => <TaskItem key={t.taskId} t={t} active={t.taskId === sel} onClick={() => setSel(t.taskId)} />)}
            </div>
          );
        })}
      </div>
      {current && <CodePane key={current.taskId} task={current} info={info[current.taskId] || {}} />}
    </div>
  );
}

export function ModelDetailScreen({ modelId, models = [], navigate = () => {} }) {
  const m = models.find((x) => x.id === modelId);
  if (!m) return <main style={{ maxWidth: 'var(--container)', margin: '0 auto', padding: '40px 24px' }}><p>модель не найдена.</p></main>;

  return (
    <main style={{ maxWidth: 'var(--container)', margin: '0 auto', padding: '0 24px' }}>
      <div style={{ paddingTop: 28 }}>
        <Button variant="ghost" size="sm" iconLeft={<Icon name="arrowLeft" size={16} />} onClick={() => navigate('leaderboard')}>Лидерборд</Button>
      </div>

      {/* Шапка модели */}
      <section style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '20px 0 32px', flexWrap: 'wrap' }}>
        <Avatar name={m.name} size={64} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <h1 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 'var(--text-h2)', fontWeight: 600, color: 'var(--ink-100)', letterSpacing: '-0.01em' }}>{m.name}</h1>
            <Badge tone="neutral" dot={false}>L1 · машина</Badge>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8, color: 'var(--ink-400)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
            <span>{m.family}</span><span>·</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--axis-o)' }}><Icon name="zap" size={13} />{m.cost}</span>
          </div>
        </div>
      </section>

      {/* Категории */}
      <section style={{ display: 'flex', gap: 18, marginBottom: 36, flexWrap: 'wrap' }}>
        <CategoryPanel title="Категория A · алгоритмика" sub="OneScript · оси S · M · O" q={m.qA} scores={m.A} axisOrder={['S', 'M', 'O']} />
        <CategoryPanel title="Категория B · платформа" sub="реальная 1С · оси S · M · O · P" q={m.qB} scores={m.B} axisOrder={['S', 'M', 'O', 'P']} />
      </section>

      {/* Браузер генераций */}
      <section style={{ paddingBottom: 8 }}>
        <h2 style={{ fontSize: 'var(--text-h3)', fontWeight: 600, color: 'var(--ink-100)', margin: '0 0 4px' }}>Что написала модель</h2>
        <p style={{ fontSize: 13, color: 'var(--ink-400)', margin: '0 0 18px' }}>Реальный код по каждой задаче — тот, что запускали против учебной базы. Выбери задачу слева.</p>
        <GenerationsBrowser modelId={m.id} />
      </section>
    </main>
  );
}
