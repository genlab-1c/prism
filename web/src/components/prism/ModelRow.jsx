import React from 'react';
import { RankBadge } from './RankBadge.jsx';
import { ScoreVector } from './ScoreVector.jsx';
import { VerifiedBadge } from './VerifiedBadge.jsx';
import { Avatar } from '../core/Avatar.jsx';

/** Shared grid template so a header row can align with ModelRows. */
export const MODEL_ROW_GRID = '52px minmax(180px, 1fr) 188px 78px 132px';

/**
 * One leaderboard row — composes RankBadge + Avatar + ScoreVector (compact)
 * + Q + the Verified seal. `model` is the row data. Hover lifts the surface.
 * The #1 row is faintly spotlit.
 */
export function ModelRow({ model = {}, onClick, style = {}, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const {
    rank = 1, name = 'Model', family = '', params = '',
    scores = {}, q = 0, verified = false, cost = '',
  } = model;
  const isTop = rank === 1;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid', gridTemplateColumns: MODEL_ROW_GRID, alignItems: 'center',
        gap: 16, padding: '14px 18px',
        background: hover ? 'var(--surface-raised)' : (isTop ? 'var(--top-tint)' : 'transparent'),
        borderBottom: '1px solid var(--line)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'background var(--dur) var(--ease)',
        ...style,
      }}
      {...rest}
    >
      {/* rank */}
      <div><RankBadge rank={rank} /></div>

      {/* model identity */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        <Avatar name={name} size={38} />
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, color: 'var(--ink-100)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>{name}</div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-400)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 1,
          }}>{[family, params].filter(Boolean).join(' · ')}</div>
        </div>
      </div>

      {/* SMOP vector */}
      <ScoreVector scores={scores} layout="compact" />

      {/* Q */}
      <div style={{ textAlign: 'right' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
          fontSize: 22, fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--ink-100)', lineHeight: 1,
        }}>{q.toFixed(2)}</div>
        {cost && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--ink-400)', marginTop: 3 }}>{cost}</div>}
      </div>

      {/* verified */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {verified
          ? <VerifiedBadge size="sm" />
          : <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>L1</span>}
      </div>
    </div>
  );
}
