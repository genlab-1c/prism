import React from 'react';

const AXIS_COLOR = { S: 'var(--axis-s)', M: 'var(--axis-m)', O: 'var(--axis-o)', P: 'var(--axis-p)' };

/**
 * Horizontal 0–10 score bar for one axis. Fill is the axis colour and
 * wipes in left→right on mount. Mono value sits at the right.
 * Pass `axis` to colour it, or `color` for an explicit fill.
 */
export function ScoreBar({ axis = 'M', value = 0, max = 10, showValue = true, showLetter = true, height = 8, style = {}, ...rest }) {
  const [w, setW] = React.useState(0);
  const pct = Math.max(0, Math.min(1, value / max)) * 100;
  const color = AXIS_COLOR[axis] || 'var(--brand)';

  React.useEffect(() => {
    const id = requestAnimationFrame(() => setW(pct));
    return () => cancelAnimationFrame(id);
  }, [pct]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, ...style }} {...rest}>
      {showLetter && (
        <span style={{
          width: 18, flex: 'none', fontFamily: 'var(--font-mono)', fontWeight: 700,
          fontSize: 13, color, textAlign: 'center',
        }}>{axis}</span>
      )}
      <div style={{
        flex: 1, height, borderRadius: 'var(--radius-pill)',
        background: 'var(--track-bg)', overflow: 'hidden',
      }}>
        <div style={{
          width: `${w}%`, height: '100%', background: color,
          borderRadius: 'var(--radius-pill)',
          transition: 'width var(--dur-slow) var(--ease-out)',
        }} />
      </div>
      {showValue && (
        <span style={{
          width: 38, flex: 'none', textAlign: 'right',
          fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
          fontSize: 13, fontWeight: 600, color: 'var(--ink-100)',
        }}>{value.toFixed(1)}</span>
      )}
    </div>
  );
}
