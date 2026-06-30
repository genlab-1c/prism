/* PRISM web — карточка-вердикт по модели: авто-нарратив из данных (insights.js),
   собранный из примитивов DS. Это «прогнал X → топ-N» в виде, которым делятся.
   Рядом — ShareBar: ссылка на модель + готовый текст поста. */
import React from 'react';
import { Icon } from '../chrome/Chrome.jsx';
import { Badge } from '../core/Badge.jsx';
import { Button } from '../core/Button.jsx';
import { Tag } from '../core/Tag.jsx';
import { VendorLogo } from './VendorLogo.jsx';
import { ScoreVector } from './ScoreVector.jsx';
import { buildInsights, narrativeText } from '../../lib/insights.js';

const BASE = import.meta.env.BASE_URL;
const fmtTokens = (n) => (n == null ? '—' : n < 1000 ? `${n}` : `${(n / 1000).toFixed(0)}k`);

// строка-вердикт: ярлык слева, чипы-модели справа
function VerdictRow({ label, color, names }) {
  if (!names?.length) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color, flex: 'none', minWidth: 64 }}>{label}</span>
      <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 6 }}>
        {names.map((n) => (
          <span key={n} style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-200)', background: 'var(--surface-sunken)', border: '1px solid var(--line)', borderRadius: 'var(--radius-xs)', padding: '2px 8px' }}>{n}</span>
        ))}
      </span>
    </div>
  );
}

function Stat({ label, value, sub, color, icon }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        {icon && <Icon name={icon} size={11} />}{label}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 19, fontWeight: 700, letterSpacing: '-0.01em', color: color || 'var(--ink-100)' }}>{value}</span>
      {sub && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>{sub}</span>}
    </div>
  );
}

export function NarrativeCard({ model, models = [], tagLabels = {} }) {
  const ins = buildInsights(model, models, tagLabels);
  const podium = ins.rankOverall <= 3;
  const rankText = podium ? `ТОП-${ins.rankOverall}` : `#${ins.rankOverall}`;

  return (
    <div id="prism-verdict-card" style={{ position: 'relative', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      {/* акцентная полоса призмы сверху */}
      <div style={{ height: 3, background: 'var(--prism)', opacity: podium ? 1 : 0.4 }} />
      <div style={{ padding: '20px 22px' }}>
        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-400)' }}>разбор прогона · L1</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--brand)', letterSpacing: '0.02em' }}>prism</span>
        </div>

        {/* герой: модель + ранг */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <VendorLogo vendor={model.vendor} name={model.name} size={52} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: 'var(--ink-100)', letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{model.name}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-400)', marginTop: 2 }}>{model.family}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 14px', borderRadius: 'var(--radius-pill)', background: podium ? 'var(--prism)' : 'var(--surface-sunken)', border: podium ? 'none' : '1px solid var(--line)', color: podium ? 'var(--brand-ink)' : 'var(--ink-200)', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, letterSpacing: '0.02em' }}>{rankText}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>из {ins.total} в общем зачёте</span>
          </div>
        </div>

        {/* вердикт: кого обходит / кому уступает */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9, margin: '18px 0', paddingTop: 16, borderTop: '1px solid var(--line)' }}>
          <VerdictRow label="обходит" color="var(--axis-o)" names={ins.beats} />
          <VerdictRow label="уступает" color="var(--ink-400)" names={ins.losesTo} />
        </div>

        {/* сильная / слабая стороны */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
          {ins.strongCat && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 13, color: 'var(--ink-200)' }}>
              <Tag color={ins.strongCat === 'B' ? 'p' : 'm'}>силён · {ins.strongCat}</Tag>
              <span>{ins.strongCat === 'B' ? 'платформа 1С — запросы, регистры, метаданные' : 'алгоритмика'}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-400)' }}>Q̄ {ins.strongQ?.toFixed(2)}</span>
              {ins.strongS === 10 && <Badge tone="ok" dot={false} size="sm">S 10 · синтаксис идеален</Badge>}
            </div>
          )}
          {ins.weakSpot && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 13, color: 'var(--ink-300)' }}>
              <Tag color="neutral">слабее · {ins.weakCat}</Tag>
              <span>проседает {ins.weakSpot.label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-400)' }}>{ins.weakSpot.axis} {ins.weakSpot.value}</span>
              {ins.weakTag && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>· «{ins.weakTag.label}»</span>}
            </div>
          )}
        </div>

        {/* экономика прогона */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 16, padding: '16px 0', borderTop: '1px solid var(--line)', borderBottom: '1px solid var(--line)' }}>
          <Stat label="за прогон" value={ins.runCostFmt} color="var(--axis-o)" icon="zap" />
          <Stat label="токены-выход" value={fmtTokens(ins.tokensOut)} sub={ins.economical ? 'по делу' : null} />
          <Stat label="время" value={ins.avgTime != null ? `${ins.avgTime}с` : '—'} sub={ins.slowest ? 'медленный' : 'на задачу'} color={ins.slowest ? 'var(--warn)' : null} icon="clock" />
          <Stat label="Q общий" value={ins.qOverall != null ? ins.qOverall.toFixed(2) : '—'} />
        </div>

        {/* множители цены — главный козырь */}
        {ins.cheaperThan.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--ink-400)' }}>дешевле</span>
            {ins.cheaperThan.map((x) => (
              <span key={x.name} style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--axis-o)', background: 'var(--axis-o-soft)', borderRadius: 'var(--radius-xs)', padding: '2px 9px' }}>
                <b>{x.mult}</b> {x.name}
              </span>
            ))}
          </div>
        )}
        {ins.cheaperThanAllAbove && (
          <p style={{ margin: '12px 0 0', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.5, color: 'var(--ink-400)' }}>
            Дешевле всех, кто выше по рейтингу — а всё, что дешевле, уступает в качестве.
          </p>
        )}

        {/* векторы SMOP по категориям */}
        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', marginTop: 18 }}>
          {model.A && <div><div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)', marginBottom: 8 }}>категория A</div><ScoreVector scores={model.A} layout="compact" /></div>}
          {model.B && <div><div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-400)', marginBottom: 8 }}>категория B</div><ScoreVector scores={model.B} layout="compact" /></div>}
        </div>
      </div>
    </div>
  );
}

/* Панель действий: ссылка на модель + готовый текст поста (тот формат, что заходит).
   В пост зашиваем версию бенчмарка и канонический адрес — атрибуция авторства. */
export function ShareBar({ model, models = [], tagLabels = {}, meta = {} }) {
  const [doneLink, setDoneLink] = React.useState(false);
  const [donePost, setDonePost] = React.useState(false);
  const url = (typeof window !== 'undefined' ? window.location.origin : '') + BASE + 'm/' + model.id;

  const flash = (set) => { set(true); setTimeout(() => set(false), 1400); };
  const copy = async (text, set) => { try { await navigator.clipboard.writeText(text); } catch (e) {} flash(set); };
  const shareLink = async () => {
    if (typeof navigator !== 'undefined' && navigator.share) {
      try { await navigator.share({ title: `${model.name} · prism`, url }); return; } catch (e) {}
    }
    copy(url, setDoneLink);
  };
  const copyPost = () => copy(narrativeText(buildInsights(model, models, tagLabels), { version: meta.version, url }), setDonePost);

  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
      <Button variant="primary" size="sm" iconLeft={<Icon name={doneLink ? 'check' : 'share'} size={15} />} onClick={shareLink}>
        {doneLink ? 'ссылка скопирована' : 'Поделиться'}
      </Button>
      <Button variant="secondary" size="sm" iconLeft={<Icon name={donePost ? 'check' : 'copy'} size={15} />} onClick={copyPost}>
        {donePost ? 'пост скопирован' : 'Скопировать пост'}
      </Button>
    </div>
  );
}
