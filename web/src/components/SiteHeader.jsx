/* PRISM web — общая шапка (островок на каждой странице).
   Сама управляет темой (dark-first, как в DS); навигация — настоящими ссылками
   (страницы сайта раздельные), активный пункт приходит пропсом `active`. */
import React from 'react';
import { Icon } from './chrome/Chrome.jsx';
import { useIsMobile } from '../lib/useMediaQuery.js';

const BASE = import.meta.env.BASE_URL;
const NAV = [
  { key: 'leaderboard', label: 'лидерборд', href: BASE },
  { key: 'methodology', label: 'методология', href: `${BASE}methodology` },
  { key: 'tasks', label: 'задачи', href: `${BASE}tasks` },
  { key: 'docs', label: 'документация', href: `${BASE}docs` },
];

function NavLink({ label, href, active, compact }) {
  const [hover, setHover] = React.useState(false);
  return (
    <a href={href} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        textDecoration: 'none', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: active ? 600 : 500,
        color: active ? 'var(--ink-100)' : (hover ? 'var(--ink-200)' : 'var(--ink-400)'),
        padding: compact ? '10px 2px' : '21px 2px', position: 'relative', letterSpacing: '0.005em',
        whiteSpace: 'nowrap', flex: 'none',
        transition: 'color var(--dur-fast) var(--ease)',
      }}>
      {label}
      {active && <span style={{ position: 'absolute', left: -2, right: -2, bottom: -1, height: 2, background: 'var(--brand)' }} />}
    </a>
  );
}

function ThemeToggle({ theme, onToggle }) {
  const [hover, setHover] = React.useState(false);
  const light = theme === 'light';
  return (
    <button onClick={onToggle} title={light ? 'Тёмная тема' : 'Светлая тема'} aria-label="Сменить тему"
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        width: 32, height: 32, display: 'grid', placeItems: 'center', cursor: 'pointer',
        borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-strong)',
        background: hover ? 'var(--surface-raised)' : 'var(--surface)',
        color: 'var(--ink-200)', transition: 'background var(--dur-fast) var(--ease)',
      }}>
      <Icon name={light ? 'moon' : 'sun'} size={16} />
    </button>
  );
}

function StarButton({ repo }) {
  const [hover, setHover] = React.useState(false);
  const url = repo?.url || 'https://github.com/genlab-1c/prism';
  return (
    <a href={url} target="_blank" rel="noreferrer"
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ display: 'inline-flex', alignItems: 'stretch', borderRadius: 'var(--radius-sm)', overflow: 'hidden', border: '1px solid var(--border-strong)', textDecoration: 'none' }}>
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 7, padding: '0 11px', height: 30,
        background: hover ? 'var(--navy-600)' : 'var(--surface-raised)', color: 'var(--ink-100)',
        fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: 500, transition: 'background var(--dur-fast) var(--ease)',
      }}>
        <span style={{ color: 'var(--one-c)' }}><Icon name="star" size={14} /></span>Star
      </span>
      {repo?.stars != null && (
        <span style={{
          display: 'inline-flex', alignItems: 'center', padding: '0 11px', height: 30, borderLeft: '1px solid var(--border-strong)',
          background: 'var(--surface)', color: 'var(--ink-100)', fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: 700,
        }}>{repo.stars}</span>
      )}
    </a>
  );
}

export default function SiteHeader({ active = 'leaderboard', version = '', repo = null }) {
  const [theme, setTheme] = React.useState(
    () => (typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme')) || 'dark',
  );
  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light';
    setTheme(next);
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('prism-theme', next); } catch (e) {}
  };
  const logo = `${BASE}assets/${theme === 'light' ? 'locklight' : 'lockdark'}.png`;
  const isMobile = useIsMobile();

  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20,
      background: 'var(--surface-translucent)', backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)', borderBottom: '1px solid var(--line)',
    }}>
      <div style={{ maxWidth: 'var(--container)', margin: '0 auto', padding: isMobile ? '8px 16px' : '0 24px', minHeight: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: isMobile ? 'wrap' : 'nowrap', rowGap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <a href={BASE} style={{ display: 'flex', alignItems: 'center' }}>
            <img src={logo} alt="PRISM" style={{ height: 26, width: 'auto', display: 'block' }} />
          </a>
          {!isMobile && <span style={{ color: 'var(--line)', fontSize: 18 }}>/</span>}
          {!isMobile && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-400)' }}>
              <span style={{ color: 'var(--ink-300)' }}>genlab-1c</span><span> / </span><span style={{ color: 'var(--ink-200)' }}>prism</span>
            </span>
          )}
        </div>
        <nav className="nav-bar" style={{ display: 'flex', gap: isMobile ? 20 : 24, alignSelf: 'stretch', alignItems: 'center', order: isMobile ? 3 : 0, flexBasis: isMobile ? '100%' : 'auto', flexWrap: 'nowrap', overflowX: isMobile ? 'auto' : 'visible', scrollbarWidth: 'none' }}>
          {NAV.map((n) => <NavLink key={n.key} label={n.label} href={n.href} active={active === n.key} compact={isMobile} />)}
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {!isMobile && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>v{version || '—'}</span>}
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <StarButton repo={repo} />
        </div>
      </div>
    </header>
  );
}
