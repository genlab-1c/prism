/* PRISM web — карта прогона: строка = задача, столбец = модель (в порядке ранга).
   Показывает то, чего не видно ни в лидерборде, ни в списке задач: какие задачи не берёт
   никто и где сильная модель неожиданно падает.

   Два режима покраски: «балл Q» (одна краска, 5 ступеней светлоты — читается и в градациях
   серого) и «исход» (та же палитра, что в воронке лидерборда).
   На узком экране столбцы сворачиваются в семейства моделей: 47 колонок дали бы клетку 4px,
   13 — 16px, в которую можно попасть пальцем. Тап по метке семейства раскрывает его поимённо.
   Размер клетки живёт в heatmap.css — на SSR ширину знает только CSS. */
import React from 'react';

const OUTCOME = {
  solved: ['решено', 'var(--axis-o)'],
  wrong: ['неверный ответ', '#d8b13e'],
  runtime: ['ошибка выполнения', '#dd7a3b'],
  compile: ['не компилируется', 'var(--danger)'],
  unknown: ['—', 'var(--ink-400)'],
};
const Q_STEPS = [8, 22, 42, 68, 100]; // % краски поверх фона — монотонно по светлоте в обеих темах
const qBand = (q) => (q == null ? 'na' : q < 2 ? 0 : q < 5 ? 1 : q < 7 ? 2 : q < 9 ? 3 : 4);
const qFill = (q) => (q == null ? null : `color-mix(in srgb, var(--brand) ${Q_STEPS[qBand(q)]}%, var(--surface-sunken))`);
const pct = (t) => (t.n ? Math.round((t.solved / t.n) * 100) : 0);
const r1 = (v) => Math.round(v * 10) / 10;
const plural = (n, one, few, many) => {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  return b === 1 ? one : many;
};

const seg = { display: 'inline-flex', gap: 2, padding: 3, background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)' };
const segBtn = (on) => ({ border: 'none', cursor: 'pointer', borderRadius: 'var(--radius-sm)', padding: '5px 11px',
  fontFamily: 'var(--font-mono)', fontSize: 11.5, fontWeight: on ? 600 : 500,
  background: on ? 'var(--surface-raised)' : 'transparent', color: on ? 'var(--ink-100)' : 'var(--ink-400)' });

function Segmented({ items, value, onChange, label }) {
  // ярлык строчными, без капса: он подписывает группу, а не спорит с кнопками за внимание
  return (
    <div className="hm-seg">
      <span className="hm-seg-label">{label}</span>
      <div style={seg} role="group" aria-label={label}>
        {items.map((it) => (
          <button key={it.key} type="button" onClick={() => onChange(it.key)}
            aria-pressed={it.key === value} style={segBtn(it.key === value)} title={it.hint}>{it.label}</button>
        ))}
      </div>
    </div>
  );
}

/* столбцы: модели поимённо / семейства / модели одного раскрытого семейства */
function buildCols(models, view, open) {
  if (view === 'models') return models.map((m, i) => ({ key: m.id, label: m.name, idx: [i] }));
  const fams = [];
  models.forEach((m, i) => {
    let f = fams.find((x) => x.name === m.family);
    if (!f) { f = { name: m.family, idx: [] }; fams.push(f); }
    f.idx.push(i);
  });
  if (open) {
    const f = fams.find((x) => x.name === open);
    return (f ? f.idx : []).map((i) => ({ key: models[i].id, label: models[i].name, idx: [i] }));
  }
  return fams.map((f) => ({ key: f.name, label: f.name.slice(0, 4), fam: f.name, idx: f.idx }));
}

/* значение клетки: одна модель — как есть; семейство — свёртка (средний Q, частый исход) */
function cellOf(task, col) {
  const cs = col.idx.map((i) => task.cells[i]).filter(Boolean);
  if (!cs.length) return null;
  if (cs.length === 1) return { ...cs[0], group: 0, solved: cs[0].o === 'solved' ? 1 : 0 };
  const qs = cs.map((c) => c.Q).filter((v) => v != null);
  const cnt = {};
  cs.forEach((c) => { cnt[c.o] = (cnt[c.o] || 0) + 1; });
  return {
    Q: qs.length ? r1(qs.reduce((a, b) => a + b, 0) / qs.length) : null,
    o: Object.entries(cnt).sort((a, b) => b[1] - a[1])[0][0],
    group: cs.length,
    solved: cs.filter((c) => c.o === 'solved').length,
  };
}

export default function TaskHeatmap({ data, onOpenTask }) {
  const models = data.models || [];
  const tasks = data.tasks || [];
  const [mode, setMode] = React.useState('q');
  const [sortBy, setSortBy] = React.useState('solved');
  const [open, setOpen] = React.useState(null);      // раскрытое семейство
  const [hi, setHi] = React.useState(null);          // подсветка одной градации легенды
  const [tip, setTip] = React.useState(null);
  const [sheet, setSheet] = React.useState(null);    // нижняя плашка (тач / узкий экран)
  const [narrow, setNarrow] = React.useState(false);
  const touch = React.useRef(false);

  // ширину знает CSS, но состав столбцов — JS: на узком экране сворачиваем в семейства.
  // SSR рисует полный вариант, matchMedia на маунте сворачивает — высота карты та же, прыжка нет.
  React.useEffect(() => {
    const mq = window.matchMedia('(max-width: 720px)');
    const apply = () => { setNarrow(mq.matches); setOpen(null); };
    apply();
    touch.current = window.matchMedia('(hover: none)').matches;
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  // состав столбцов больше не переключают руками: узкий экран сам сворачивает модели в семейства
  const view = narrow ? 'fam' : 'models';
  const cols = React.useMemo(() => buildCols(models, view, open), [models, view, open]);
  const famCount = React.useMemo(() => new Set(models.map((m) => m.family)).size, [models]);
  const gens = React.useMemo(() => tasks.reduce((sum, t) => sum + (t.n || 0), 0), [tasks]);
  const rows = React.useMemo(() => {
    const a = [...tasks];
    if (sortBy === 'solved') a.sort((x, y) => x.solved / x.n - y.solved / y.n || x.id.localeCompare(y.id));
    return a;
  }, [tasks, sortBy]);

  const legend = React.useMemo(() => {
    const all = [];
    for (const t of rows) for (const c of cols) { const v = cellOf(t, c); if (v) all.push(v); }
    return mode === 'q'
      ? [[0, 'Q 0–2'], [1, 'Q 2–5'], [2, 'Q 5–7'], [3, 'Q 7–9'], [4, 'Q 9–10']]
        .map(([b, label]) => ({ key: b, label, color: qFill([1, 3.5, 6, 8, 10][b]), n: all.filter((c) => qBand(c.Q) === b).length }))
      : Object.entries(OUTCOME).filter(([k]) => k !== 'unknown')
        .map(([k, [label, color]]) => ({ key: k, label, color, n: all.filter((c) => c.o === k).length }));
  }, [rows, cols, mode]);

  const useSheet = () => touch.current || narrow;

  const describe = (task, col) => {
    const c = cellOf(task, col);
    if (!c) return null;
    const who = c.group
      ? `${col.fam} · ${c.group} моделей · решили ${c.solved}`
      : `${models[col.idx[0]].name} · #${col.idx[0] + 1}`;
    const line = c.group
      ? `средний Q ${c.Q ?? '—'} · чаще всего ${(OUTCOME[c.o] || OUTCOME.unknown)[0]}`
      : `Q ${c.Q ?? '—'} · ${(OUTCOME[c.o] || OUTCOME.unknown)[0]}${c.t ? ` · тесты ${c.p}/${c.t}` : ''}${c.sec != null ? ` · ${c.sec} с` : ''}`;
    const why = !c.group && c.o !== 'solved' ? c.why : null;
    return { title: `${task.id} · ${task.name}`, who, line, why, modelId: c.group ? null : models[col.idx[0]].id };
  };

  const cellAt = (el) => {
    const t = rows.find((x) => x.id === el.dataset.t);
    const col = cols[Number(el.dataset.c)];
    return t && col ? { task: t, col } : null;
  };

  const onMove = (e) => {
    if (useSheet()) return;
    const el = e.target.closest('[data-c]');
    if (!el) { setTip(null); return; }
    const at = cellAt(el);
    if (!at) return;
    setTip({ ...describe(at.task, at.col), x: e.clientX, y: e.clientY });
  };

  const onClick = (e) => {
    const head = e.target.closest('[data-fam]');
    if (head) { setOpen(head.dataset.fam); return; }
    const lab = e.target.closest('[data-task]');
    if (lab) { e.preventDefault(); onOpenTask?.(lab.dataset.task); return; }
    const el = e.target.closest('[data-c]');
    if (!el) return;
    const at = cellAt(el);
    if (!at) return;
    const d = describe(at.task, at.col);
    if (useSheet()) {
      const key = `${at.task.id}/${el.dataset.c}`;
      if (sheet?.key === key) { setSheet(null); onOpenTask?.(at.task.id, d.modelId); }
      else setSheet({ key, taskId: at.task.id, ...d });
    } else onOpenTask?.(at.task.id, d.modelId);
  };

  const gridStyle = { gridTemplateColumns: `var(--label) repeat(${cols.length}, minmax(var(--cell-min), 1fr))` };
  const solvedRange = tasks.length ? `${Math.min(...tasks.map(pct))}% до ${Math.max(...tasks.map(pct))}%` : '—';

  return (
    <section style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', marginBottom: 26 }}>
      <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--line)' }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: 'var(--ink-100)' }}>Карта прогона</h2>
        <p style={{ margin: '4px 0 0', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)' }}>
          {gens} {plural(gens, 'генерация', 'генерации', 'генераций')} · {tasks.length} {plural(tasks.length, 'задача', 'задачи', 'задач')} × {models.length} {plural(models.length, 'модель', 'модели', 'моделей')}
          {narrow ? ` · сгруппированы в ${famCount} ${plural(famCount, 'семейство', 'семейства', 'семейств')}` : ''} · одна клетка — одна генерация
        </p>
        <div className="hm-toolbar">
          <Segmented label="цвет:" value={mode} onChange={(v) => { setMode(v); setHi(null); }}
            items={[
              { key: 'q', label: 'по баллу', hint: 'итоговый балл SMOP за генерацию: 0–10' },
              { key: 'o', label: 'по исходу', hint: 'решено · неверный ответ · ошибка выполнения · не компилируется' },
            ]} />
          <Segmented label="порядок:" value={sortBy} onChange={setSortBy}
            items={[
              { key: 'solved', label: 'трудные сверху', hint: 'по доле моделей, прошедших все скрытые тесты задачи' },
              { key: 'id', label: 'по номеру', hint: 'A1…A15, затем B1…B20' },
            ]} />
        </div>
      </div>

      {open && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 18px 0', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-300)' }}>
          <button type="button" onClick={() => setOpen(null)}
            style={{ background: 'var(--chip-bg)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', cursor: 'pointer', padding: '4px 10px', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-200)' }}>
            ← ко всем семействам
          </button>
          <span>{open} · {cols.length} моделей поимённо</span>
        </div>
      )}

      <div className="hm-scroll">
        <div className={`hm${cols.length <= 13 ? ' is-narrow' : ''}`} style={gridStyle} role="img"
          aria-label={`Карта прогона: ${tasks.length} задач на ${models.length} моделях, решаемость от ${solvedRange}`}
          onMouseMove={onMove} onMouseLeave={() => setTip(null)} onClick={onClick}>
          <div className="hm-corner" />
          {cols.map((c) => (
            <div key={c.key} className={`hm-colhead${c.fam ? ' is-group' : ''}`} data-fam={c.fam || undefined}
              title={c.fam ? `${c.fam} · ${c.idx.length} моделей — раскрыть` : c.label}>
              {c.label.length > 17 ? `${c.label.slice(0, 16)}…` : c.label}
            </div>
          ))}
          {rows.map((t, ri) => (
            <React.Fragment key={t.id}>
              {sortBy === 'id' && ri > 0 && rows[ri - 1].cat !== t.cat && <div className="hm-sep" />}
              <a className="hm-rowlab" href="#" data-task={t.id} title={`${t.id} · ${t.name}`}>
                <span className="tid">{t.id}</span>
                <span className="nm">{t.name}</span>
                <span className="pc">{pct(t)}%</span>
              </a>
              {cols.map((c, ci) => {
                const v = cellOf(t, c);
                const color = !v ? null : mode === 'q' ? qFill(v.Q) : (OUTCOME[v.o] || OUTCOME.unknown)[1];
                const dim = hi != null && v && !(mode === 'q' ? hi === qBand(v.Q) : hi === v.o);
                return <div key={c.key} className={`hm-cell${color ? '' : ' is-empty'}`} data-t={t.id} data-c={ci}
                  style={{ background: color || undefined, opacity: dim ? 0.13 : undefined }} />;
              })}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="hm-legend">
        {legend.map((it) => (
          <button key={it.key} type="button" onClick={() => setHi(hi === it.key ? null : it.key)} aria-pressed={hi === it.key}>
            <span className="sw" style={{ background: it.color }} />
            {it.label} · {it.n}
          </button>
        ))}
      </div>
      {cols[0]?.idx.length > 1 && (
        <p className="hm-hint">
          {mode === 'q' ? 'клетка — средний балл семейства; нажатие на его метку раскрывает модели поимённо' : 'клетка — самый частый исход в семействе'}
        </p>
      )}

      {tip && !useSheet() && (
        <div className="hm-tip" style={{ opacity: 1, left: Math.min(tip.x + 14, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 300), top: Math.max(8, tip.y - 90) }}>
          <div className="t1">{tip.title}</div>
          <div className="t2">{tip.who}</div>
          <div className="t3">{tip.line}</div>
          {tip.why && <div className="t4">{tip.why}</div>}
        </div>
      )}

      <div className={`hm-sheet${sheet ? ' is-open' : ''}`} role="dialog" aria-label="Клетка карты" aria-hidden={!sheet}>
        {sheet && (
          <>
            <div className="s1">{sheet.title}</div>
            <div className="s2">{sheet.who}</div>
            <div className="s3">{sheet.line}</div>
            {sheet.why && <div className="s4">{sheet.why}</div>}
            <div className="row">
              <button type="button" onClick={() => { const s = sheet; setSheet(null); onOpenTask?.(s.taskId, s.modelId); }}
                style={{ flex: 1, background: 'var(--brand)', color: 'var(--brand-ink)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '8px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                открыть задачу {sheet.taskId} →
              </button>
              <button type="button" onClick={() => setSheet(null)}
                style={{ background: 'var(--chip-bg)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-300)', cursor: 'pointer' }}>
                закрыть
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
