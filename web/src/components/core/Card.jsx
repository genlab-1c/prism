import React from 'react';

/**
 * Surface container. Hairline border, surface bg, 12px radius.
 * `interactive` lifts surface + brightens border on hover.
 * `glow` adds the cyan spotlight (use once — e.g. the #1 leader).
 */
export function Card({ children, interactive = false, glow = false, padding = 20, style = {}, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onMouseEnter={() => interactive && setHover(true)}
      onMouseLeave={() => interactive && setHover(false)}
      style={{
        background: hover ? 'var(--surface-raised)' : 'var(--surface)',
        border: `1px solid ${glow ? 'transparent' : (hover ? 'var(--border-strong)' : 'var(--line)')}`,
        borderRadius: 'var(--radius-lg)',
        padding,
        boxShadow: glow ? 'var(--glow-brand)' : 'var(--shadow-sm)',
        transition: 'background var(--dur) var(--ease), border-color var(--dur) var(--ease)',
        cursor: interactive ? 'pointer' : 'default',
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
