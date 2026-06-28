import React from 'react';

/**
 * The "Verified" trust seal — the L2 sign that an expert checked the
 * machine. Emerald check in a soft capsule. This is a meaning-bearing
 * mark, not decoration: only on results an expert actually validated.
 */
export function VerifiedBadge({ label = 'Verified', size = 'md', style = {}, ...rest }) {
  const dims = size === 'sm'
    ? { font: 11, disc: 14, pad: '3px 10px 3px 6px' }
    : { font: 12.5, disc: 16, pad: '4px 12px 4px 7px' };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: dims.pad, borderRadius: 'var(--radius-pill)',
      background: 'var(--ok-soft)', border: '1px solid rgba(52,211,153,0.40)',
      color: 'var(--verified)', fontFamily: 'var(--font-sans)',
      fontWeight: 600, fontSize: dims.font, letterSpacing: '0.01em', whiteSpace: 'nowrap',
      ...style,
    }} {...rest}>
      <svg width={dims.disc} height={dims.disc} viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"
        style={{ flex: 'none' }} aria-hidden="true">
        <path d="M20 6 9 17l-5-5" />
      </svg>
      {label}
    </span>
  );
}
