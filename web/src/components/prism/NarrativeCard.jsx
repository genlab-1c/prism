/* PRISM web — карточка-вердикт по модели: авто-нарратив из данных (insights.js),
   собранный из примитивов DS. Это «прогнал X → топ-N» в виде, которым делятся.
   Рядом — ShareBar: ссылка на модель + готовый текст поста. */
import React from 'react';
import { Icon } from '../chrome/Chrome.jsx';
import { Button } from '../core/Button.jsx';
import { VendorLogo } from './VendorLogo.jsx';
import { buildInsights } from '../../lib/insights.js';
import { useIsMobile } from '../../lib/useMediaQuery.js';

const BASE = import.meta.env.BASE_URL;

// строка-вердикт: ярлык слева, чипы-модели справа
function VerdictRow({ label, color, names, mHref }) {
  if (!names?.length) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color, flex: 'none', minWidth: 64 }}>{label}</span>
      <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 6 }}>
        {names.map((n) => (
          <a key={n} href={mHref?.(n) || undefined} style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-200)', background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-xs)', padding: '2px 8px', textDecoration: 'none', cursor: mHref?.(n) ? 'pointer' : 'default' }}>{n}</a>
        ))}
      </span>
    </div>
  );
}

// категория по-человечески: что это + «решает X% задач» (понятнее, чем «Q 9.78»)
function CatBlock({ title, desc, solved, s, q }) {
  const pct = solved != null ? Math.round(solved * 100) : null;
  const good = pct != null ? pct >= 65 : (q ?? 0) >= 7;
  const line = pct != null ? `решает ${pct}% задач` : (q != null ? `оценка ${q.toFixed(1)} из 10` : 'не измерялось');
  return (
    <div style={{ flex: 1, minWidth: 200, background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', padding: '10px 13px' }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-100)' }}>{title}</div>
      <div style={{ fontSize: 11.5, color: 'var(--ink-400)', marginTop: 2, lineHeight: 1.35 }}>{desc}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 14, fontWeight: 700, color: good ? 'var(--axis-o)' : 'var(--axis-p)', marginTop: 7 }}>{line}</div>
    </div>
  );
}

// значение экономики + человеческий смысл под ним (не голая цифра)
function EconStat({ label, value, meaning, tone, icon }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 3, minWidth: 0 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>{icon && <Icon name={icon} size={11} />}{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 19, fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--ink-100)' }}>{value}</span>
      {meaning && <span style={{ fontSize: 11, fontWeight: 600, color: tone || 'var(--ink-400)' }}>{meaning}</span>}
    </div>
  );
}

const fmtTok = (n) => (n == null ? '—' : n >= 1000 ? `${(n / 1000).toFixed(1)}к` : `${Math.round(n)}`);
const median = (arr) => {
  const s = [...arr].sort((a, b) => a - b); const n = s.length;
  return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null;
};
const TIER_TEXT = {
  cost: ['дешевле большинства', 'средняя цена', 'дороже большинства'],
  time: ['быстрее большинства', 'средняя скорость', 'медленнее большинства'],
  tokens: ['экономнее большинства', 'средний расход', 'многословнее большинства'],
};
// ярлык по отношению к МЕДИАНЕ (не к рангу — цены скошены длинным хвостом дорогих моделей).
// «меньше = лучше»: заметно ниже медианы → лучше, заметно выше → хуже, рядом → средне.
function tier(models, key, val, kind) {
  const vals = models.map((m) => m.econ?.[key]).filter((v) => v != null && v > 0);
  const med = median(vals);
  if (med == null || val == null || val <= 0) return null;
  const ratio = val / med;
  const [better, mid, worse] = TIER_TEXT[kind];
  if (ratio <= 0.6) return { text: better, tone: 'var(--axis-o)' };
  if (ratio <= 1.6) return { text: mid, tone: 'var(--ink-300)' };
  return { text: worse, tone: 'var(--axis-p)' };
}

const qualityWord = (q) => (q == null ? '—' : q >= 8.5 ? 'отлично' : q >= 7 ? 'хорошо' : q >= 5 ? 'средне' : 'слабо');

// человеческие названия осей + что балл значит на трёх уровнях
const AXIS_NAME = { S: 'Синтаксис', M: 'Логика', O: 'Оптимальность', P: 'Платформа 1С' };
const AXIS_SAY = {
  S: { top: 'код всегда компилируется', hi: 'почти всегда пишет компилируемый код', mid: 'иногда синтаксические ошибки в коде', lo: 'часто не компилируется' },
  M: { top: 'логика всегда верна — все тесты пройдены', hi: 'решения логически верны, проходят скрытые тесты', mid: 'логика местами хромает — часть тестов не проходит', lo: 'часто выдаёт неверный результат' },
  O: { top: 'оптимальный код без лишней работы', hi: 'эффективный код — без лишних переборов и запросов в цикле', mid: 'местами лишние обращения к данным', lo: 'неоптимально — запросы в цикле, лишние переборы' },
  P: { top: 'безупречно работает с метаданными 1С', hi: 'уверенно работает с объектами и метаданными 1С', mid: 'иногда ошибается в объектах и полях 1С', lo: 'путается в метаданных — обращается к несуществующим полям и объектам' },
};

// вердикт по одной оси: топ (≈10) / плюс / минус, с учётом СИЛЬНОГО расхождения между A и B
// (модель бывает отличной в алгоритмике и провальной в платформе — тогда «отлично там, но слабо тут»).
function axisLine(ax, a, b, ins) {
  const vals = [a, b].filter((v) => v != null);
  if (!vals.length) return null;
  const avg = vals.reduce((x, y) => x + y, 0) / vals.length;
  const say = AXIS_SAY[ax];
  if (a != null && b != null && Math.abs(a - b) >= 3.5) {
    const aBetter = a >= b;
    return { side: 'minus', text: `отлично ${aBetter ? 'в алгоритмике' : 'в платформенных задачах'}, но слабо ${aBetter ? 'в платформенных задачах' : 'в алгоритмике'}` };
  }
  if (avg >= 9.7) return { side: 'plus', text: say.top || say.hi };
  if (avg >= 8) return { side: 'plus', text: say.hi };
  let t = avg >= 6 ? say.mid : say.lo;
  if (ax === ins.weakSpot?.axis && ins.weakTag) t += ` (слабее на «${ins.weakTag.label}»)`;
  return { side: 'minus', text: t };
}

// подробный вердикт: по каждой оси — плюс/минус простым языком. Представитель оси — СРЕДНЕЕ A и B
// (без перекоса в худшую категорию, чтобы согласовать с долей решённых). Сильная категория — тоже по solved%.
function verdictDetail(model, ins) {
  const pluses = [], minuses = [];
  for (const ax of ['M', 'O', 'P', 'S']) {
    const line = axisLine(ax, model.A?.[ax], model.B?.[ax], ins);
    if (!line) continue;
    (line.side === 'plus' ? pluses : minuses).push({ ax, name: AXIS_NAME[ax], text: line.text });
  }
  // сильная категория — по доле решённых (то, что показано ниже в карточке), а не по Q — иначе рассинхрон
  const aS = model.A?.solved, bS = model.B?.solved;
  const strongCat = (aS != null && bS != null) ? (aS >= bS ? 'A' : 'B') : (ins.strongCat || 'A');
  const strong = strongCat === 'A' ? 'алгоритмике' : 'платформенных задачах';
  let lead;
  const leaderCut = Math.max(3, Math.ceil(ins.total * 0.15)); // «лидер» — топ ~15%, а не жёсткая тройка (#4/31 — тоже лидер)
  if (ins.rankOverall === 1) lead = `Лучший результат прогона по качеству кода 1С. Сильнее всего в ${strong}.`;
  else if (ins.rankOverall <= leaderCut) lead = `Один из лидеров рейтинга. Сильнее всего в ${strong}.`;
  else if (ins.rankOverall <= Math.ceil(ins.total * 0.5)) lead = `Выше среднего. Увереннее в ${strong}.`;
  else lead = `Ниже среднего по коду 1С. Лучше в ${strong}.`;
  return { lead, pluses, minuses };
}

// группа вердикта (Плюсы / Минусы): заголовок + список «маркер · Ось — что значит»
function VGroup({ title, tone, mark, items }) {
  if (!items.length) return null;
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: tone, marginBottom: 7 }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map((it) => (
          <div key={it.ax} style={{ display: 'flex', gap: 8, fontSize: 12.5, lineHeight: 1.4 }}>
            <span style={{ flex: 'none', fontFamily: 'var(--font-mono)', fontWeight: 700, color: tone }}>{mark}</span>
            <span style={{ color: 'var(--ink-300)' }}><b style={{ color: 'var(--ink-100)' }}>{it.name}</b> — {it.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function NarrativeCard({ model, models = [], tagLabels = {} }) {
  const isMobile = useIsMobile();
  const ins = buildInsights(model, models, tagLabels);
  const podium = ins.rankOverall <= 3;
  const rankText = podium ? `ТОП-${ins.rankOverall}` : `#${ins.rankOverall}`;
  const costTier = tier(models, 'genCost', model.econ?.genCost, 'cost');
  const timeTier = tier(models, 'avgTime', model.econ?.avgTime, 'time');
  const tokTier = tier(models, 'tokPerGen', model.econ?.tokPerGen, 'tokens');
  const vd = verdictDetail(model, ins);
  // клик по имени модели в чипах сравнения → её страница (реальный роут /m/<id>)
  const idByName = React.useMemo(() => Object.fromEntries(models.map((m) => [m.name, m.id])), [models]);
  const mHref = (name) => (idByName[name] ? `${BASE}m/${idByName[name]}` : null);

  return (
    <div id="prism-verdict-card" style={{ position: 'relative', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      {/* акцентная полоса призмы сверху */}
      <div style={{ height: 3, background: 'var(--prism)', opacity: podium ? 1 : 0.4 }} />
      <div style={{ padding: isMobile ? '16px 14px' : '20px 22px' }}>
        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-400)' }}>разбор оценки · L1</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--brand)', letterSpacing: '0.02em' }}>prism</span>
        </div>

        {/* герой: модель + ранг */}
        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 12 : 16, flexWrap: 'wrap' }}>
          <VendorLogo vendor={model.vendor} name={model.name} size={isMobile ? 44 : 52} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: isMobile ? 18 : 22, fontWeight: 700, color: 'var(--ink-100)', letterSpacing: '-0.01em', lineHeight: 1.15, ...(isMobile ? { whiteSpace: 'normal', wordBreak: 'break-word' } : { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }) }}>{model.name}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-400)', marginTop: 2 }}>{model.family}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 14px', borderRadius: 'var(--radius-pill)', background: podium ? 'var(--prism)' : 'var(--surface-sunken)', border: podium ? 'none' : '1px solid var(--line)', color: podium ? 'var(--brand-ink)' : 'var(--ink-200)', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, letterSpacing: '0.02em' }}>{rankText}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>из {ins.total} моделей</span>
          </div>
        </div>

        {/* вердикт: лид одной фразой + подробные плюсы/минусы по осям */}
        <div style={{ margin: '16px 0 0' }}>
          <p style={{ margin: 0, fontSize: 14, color: 'var(--ink-100)', lineHeight: 1.5 }}>{vd.lead}</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: isMobile ? 12 : 16, marginTop: isMobile ? 10 : 12 }}>
            <VGroup title="Плюсы" tone="var(--axis-o)" mark="+" items={vd.pluses} />
            <VGroup title="Минусы" tone="var(--axis-p)" mark="−" items={vd.minuses} />
          </div>
        </div>

        {/* что умеет — по-человечески, в доле решённых задач */}
        <div style={{ display: 'flex', gap: isMobile ? 10 : 12, flexWrap: 'wrap', margin: isMobile ? '14px 0' : '18px 0' }}>
          {model.A && <CatBlock title="Алгоритмика" desc="Чистый код: расчёты, строки, коллекции — без базы 1С." solved={model.A.solved} s={model.A.S} q={model.qA} />}
          {model.B && <CatBlock title="Платформенные задачи" desc="Запросы, регистры, работа с реальной базой 1С." solved={model.B.solved} s={model.B.S} q={model.qB} />}
        </div>

        {/* цена · скорость · общая оценка — с человеческим смыслом */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: isMobile ? 12 : 16, padding: isMobile ? '14px 0' : '16px 0', borderTop: '1px solid var(--line)', borderBottom: '1px solid var(--line)' }}>
          <EconStat label="цена ответа" value={ins.genCostFmt} meaning={costTier?.text} tone={costTier?.tone} icon="zap" />
          <EconStat label="скорость" value={ins.avgTime != null ? `${ins.avgTime} с` : '—'} meaning={timeTier?.text} tone={timeTier?.tone} icon="clock" />
          <EconStat label="токенов на ответ" value={fmtTok(model.econ?.tokPerGen)} meaning={tokTier?.text} tone={tokTier?.tone} />
          <EconStat label="общая оценка" value={ins.qOverall != null ? `${ins.qOverall.toFixed(1)} / 10` : '—'} meaning={qualityWord(ins.qOverall)} tone={(ins.qOverall ?? 0) >= 7 ? 'var(--axis-o)' : 'var(--ink-400)'} />
        </div>

        {/* дешевле конкретных конкурентов — понятный козырь */}
        {ins.cheaperThan.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--ink-400)' }}>дешевле</span>
            {ins.cheaperThan.map((x) => (
              <a key={x.name} href={mHref(x.name) || undefined} style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--axis-o)', background: 'var(--axis-o-soft)', borderRadius: 'var(--radius-xs)', padding: '2px 9px', textDecoration: 'none', cursor: mHref(x.name) ? 'pointer' : 'default' }}>
                <b>{x.mult}</b> {x.name}
              </a>
            ))}
          </div>
        )}

        {/* дороже конкретных конкурентов — честная симметрия «дешевле», а не только козыри */}
        {(ins.pricierThan || []).length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: ins.cheaperThan.length ? 8 : 14 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--ink-400)' }}>дороже</span>
            {ins.pricierThan.map((x) => (
              <a key={x.name} href={mHref(x.name) || undefined} style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--warn)', background: 'color-mix(in srgb, var(--warn) 12%, transparent)', borderRadius: 'var(--radius-xs)', padding: '2px 9px', textDecoration: 'none', cursor: mHref(x.name) ? 'pointer' : 'default' }}>
                <b>{x.mult}</b> {x.name}
              </a>
            ))}
          </div>
        )}

        {/* с кем сравнивать: сильнее / слабее по общему качеству */}
        {(ins.beats.length > 0 || ins.losesTo.length > 0) && (
          <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--line)' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)', marginBottom: 10 }}>по общему качеству кода 1С</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              <VerdictRow label="сильнее" color="var(--axis-o)" names={ins.beats} mHref={mHref} />
              <VerdictRow label="слабее" color="var(--ink-400)" names={ins.losesTo} mHref={mHref} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* Панель действий: ссылка на модель + готовый текст поста (тот формат, что заходит).
   В пост зашиваем версию бенчмарка и канонический адрес — атрибуция авторства. */
export function ShareBar({ model }) {
  const [doneLink, setDoneLink] = React.useState(false);
  const url = (typeof window !== 'undefined' ? window.location.origin : '') + BASE + 'm/' + model.id;

  const flash = (set) => { set(true); setTimeout(() => set(false), 1400); };
  const shareLink = async () => {
    if (typeof navigator !== 'undefined' && navigator.share) {
      try { await navigator.share({ title: `${model.name} · prism`, url }); return; } catch (e) { /* отменили — копируем */ }
    }
    try { await navigator.clipboard.writeText(url); } catch (e) { /* нет буфера */ }
    flash(setDoneLink);
  };

  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
      <Button variant="primary" size="sm" iconLeft={<Icon name={doneLink ? 'check' : 'share'} size={15} />} onClick={shareLink}>
        {doneLink ? 'ссылка скопирована' : 'Поделиться'}
      </Button>
    </div>
  );
}
