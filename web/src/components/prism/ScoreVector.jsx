import React from 'react';
import { ScoreBar } from './ScoreBar.jsx';

const AXES = ['S', 'M', 'O', 'P'];
const AXIS_COLOR = { S: 'var(--axis-s)', M: 'var(--axis-m)', O: 'var(--axis-o)', P: 'var(--axis-p)' };

/**
 * The full SMOP result — four axes at once. PRISM's core principle: the
 * vector is the real result, not a single number.
 *  - layout="bars"    → four stacked animated bars (model detail)
 *  - layout="compact" → inline mini meters + mono values (leaderboard rows)
 * `scores` is { S, M, O, P } (a null/undefined axis renders as «—», "не измерено").
 */
export function ScoreVector({ scores = {}, layout = 'compact', axes = AXES, style = {}, ...rest }) {
  if (layout === 'bars') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, ...style }} {...rest}>
        {axes.map(a => (
          <ScoreBar key={a} axis={a} value={scores[a] ?? 0} />
        ))}
      </div>
    );
  }

  // compact
  return (
    <div style={{ display: 'flex', gap: 16, ...style }} {...rest}>
      {axes.map(a => {
        const v = scores[a];
        const has = v !== null && v !== undefined;
        const color = AXIS_COLOR[a];
        return (
          <div key={a} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 30 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
              fontSize: 13, fontWeight: 600, color: has ? 'var(--ink-100)' : 'var(--ink-400)',
            }}>{has ? v.toFixed(1) : '—'}</span>
            <div style={{ width: 30, height: 4, borderRadius: 'var(--radius-pill)', background: 'var(--track-bg)', overflow: 'hidden' }}>
              <div style={{
                width: has ? `${Math.max(0, Math.min(1, v / 10)) * 100}%` : 0,
                height: '100%', background: color, borderRadius: 'var(--radius-pill)',
              }} />
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, color }}>{a}</span>
          </div>
        );
      })}
    </div>
  );
}
