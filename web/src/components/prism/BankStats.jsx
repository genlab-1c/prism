/* PRISM web — статистика по банку задач: как распределены баллы моделей по всему прогону.
   Те же агрегаты, что в аудите корпуса (docs/audit-2026-09.md, раздел 4а): медиана,
   среднее, квартили, разброс, крайние значения. Всё считается здесь из task_matrix.json,
   чисел в коде нет: добавилась модель — статистика пересчиталась сама.

   Форма — полоса распределения, а не таблица: точка на каждую модель, заливка между
   квартилями, черта медианы. Так видно не только «где середина», но и где сгущаются модели
   и кто отстал. Наведение на точку подсвечивает ту же модель во всех трёх полосах.
   Последняя полоса — задачи: какая доля моделей решает каждую.
   На телефоне точки и столбик цифр не читаются: остаются медиана, полоса квартилей и одна
   строка словами (.bs-mob), всё прочее прячет CSS. */
import React from 'react';

const r2 = (v) => (v == null || Number.isNaN(v) ? '—' : v.toFixed(2));

// квантиль с линейной интерполяцией (как numpy/Excel по умолчанию)
function quantile(sorted, p) {
  if (!sorted.length) return null;
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

function describe(values) {
  const v = values.filter((x) => typeof x === 'number').sort((a, b) => a - b);
  const n = v.length;
  if (!n) return null;
  const mean = v.reduce((s, x) => s + x, 0) / n;
  const sd = n > 1 ? Math.sqrt(v.reduce((s, x) => s + (x - mean) ** 2, 0) / (n - 1)) : 0;
  return { n, mean, median: quantile(v, 0.5), q1: quantile(v, 0.25), q3: quantile(v, 0.75), sd, min: v[0], max: v[n - 1] };
}

// точки раскладываем по пяти дорожкам по порядку значения: соседние по баллу модели
// оказываются на разной высоте и не слипаются в одно пятно у правого края
const LANES = [50, 18, 82, 34, 66];

function Strip({ points, stat, max, fmt, hover, onHover, ticks }) {
  const x = (v) => `${(v / max) * 100}%`;
  const sorted = [...points].sort((a, b) => a.v - b.v);
  const active = sorted.find((p) => p.id === hover);
  return (
    <div className="bs-strip">
      <div className="bs-track">
        {ticks.map((t) => <span key={t} className="bs-grid" style={{ left: x(t) }} />)}
        <span className="bs-whisker" style={{ left: x(stat.min), width: `${((stat.max - stat.min) / max) * 100}%` }} />
        <span className="bs-box" style={{ left: x(stat.q1), width: `${((stat.q3 - stat.q1) / max) * 100}%` }} />
        {sorted.map((p, i) => (
          <button
            key={p.id}
            type="button"
            className={`bs-dot${hover === p.id ? ' is-on' : ''}${hover && hover !== p.id ? ' is-dim' : ''}`}
            style={{ left: x(p.v), top: `${LANES[i % LANES.length]}%` }}
            aria-label={`${p.label}: ${fmt(p.v)}`}
            onMouseEnter={() => onHover(p.id)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(p.id)}
            onBlur={() => onHover(null)}
          />
        ))}
        <span className="bs-median" style={{ left: x(stat.median) }} title={`медиана ${fmt(stat.median)}`} />
        {active && (
          <span className={`bs-tip${active.v / max > 0.7 ? ' is-left' : ''}`} style={{ left: x(active.v) }}>
            {active.label} · <b>{fmt(active.v)}</b>
          </span>
        )}
      </div>
    </div>
  );
}

function Axis({ ticks, max, fmt }) {
  return (
    <div className="bs-axis" aria-hidden="true">
      {ticks.map((t) => <span key={t} style={{ left: `${(t / max) * 100}%` }}>{fmt(t)}</span>)}
    </div>
  );
}

const ROWS = [['q', 'общий'], ['qA', 'категория A'], ['qB', 'категория B']];
const Q_TICKS = [0, 2, 4, 6, 8, 10];
const PCT_TICKS = [0, 0.25, 0.5, 0.75, 1];
const pct = (v) => `${Math.round(v * 100)}%`;

export default function BankStats({ data }) {
  const [hover, setHover] = React.useState(null);
  const models = data?.models || [];
  const tasks = (data?.tasks || []).filter((t) => t.n);

  const rows = React.useMemo(() => ROWS.map(([key, label]) => {
    const points = models.filter((m) => typeof m[key] === 'number').map((m) => ({ id: m.id, label: m.name, v: m[key] }));
    return { key, label, points, stat: describe(points.map((p) => p.v)) };
  }), [models]);

  const taskPoints = tasks.map((t) => ({ id: `task:${t.id}`, label: `${t.id} ${t.name}`, v: t.solved / t.n }));
  const taskStat = describe(taskPoints.map((p) => p.v));
  if (!rows[0].stat) return null;

  const byShare = [...tasks].sort((a, b) => a.solved / a.n - b.solved / b.n);
  const hardest = byShare[0], easiest = byShare[byShare.length - 1];

  return (
    <section className="bank-stats">
      <div className="bank-stats-head">
        <h2>Статистика по банку задач</h2>
        <p>{rows[0].stat.n} моделей · {tasks.length} задач<span className="bs-legend"> · точка — модель, заливка — средние 50%, черта — медиана</span></p>
      </div>

      <div className="bs-rows">
        {rows.map(({ key, label, points, stat }) => stat && (
          <div key={key} className="bs-row">
            <div className="bs-name">
              <span className="bs-label">{label}</span>
              <span className="bs-big">{r2(stat.median)}</span>
              <span className="bs-cap">медиана Q</span>
            </div>
            <Strip points={points} stat={stat} max={10} fmt={r2} hover={hover} onHover={setHover} ticks={Q_TICKS} />
            <p className="bs-mob">половина моделей между <b>{r2(stat.q1)}</b> и <b>{r2(stat.q3)}</b> · среднее {r2(stat.mean)}</p>
            <dl className="bs-facts">
              <div><dt>среднее</dt><dd>{r2(stat.mean)}</dd></div>
              <div><dt>квартили</dt><dd>{r2(stat.q1)}…{r2(stat.q3)}</dd></div>
              <div><dt>разброс <span className="bs-sym">σ</span></dt><dd>{r2(stat.sd)}</dd></div>
              <div><dt>мин / макс</dt><dd>{r2(stat.min)} / {r2(stat.max)}</dd></div>
            </dl>
          </div>
        ))}
        <div className="bs-row bs-row-axis">
          <span />
          <Axis ticks={Q_TICKS} max={10} fmt={(t) => t} />
          <span />
        </div>
      </div>

      {taskStat && (
        <div className="bs-rows bs-tasks">
          <div className="bs-row">
            <div className="bs-name">
              <span className="bs-label">задачи</span>
              <span className="bs-big">{pct(taskStat.median)}</span>
              <span className="bs-cap">медиана решивших</span>
            </div>
            <Strip points={taskPoints} stat={taskStat} max={1} fmt={pct} hover={hover} onHover={setHover} ticks={PCT_TICKS} />
            <p className="bs-mob">половина задач решается долей от <b>{pct(taskStat.q1)}</b> до <b>{pct(taskStat.q3)}</b> моделей</p>
            <dl className="bs-facts is-tasks">
              <div><dt>труднее всех</dt><dd>{hardest.id} · {pct(hardest.solved / hardest.n)}</dd></div>
              <div><dt>легче всех</dt><dd>{easiest.id} · {pct(easiest.solved / easiest.n)}</dd></div>
            </dl>
          </div>
          <div className="bs-row bs-row-axis">
            <span />
            <Axis ticks={PCT_TICKS} max={1} fmt={pct} />
            <span />
          </div>
        </div>
      )}
    </section>
  );
}
