/* PRISM web — простой хук медиа-запроса для адаптивных раскладок в инлайн-стилях.
   SSR-безопасен: до монтирования возвращает false (десктоп-раскладка по умолчанию). */
import React from 'react';

export function useMediaQuery(query) {
  const [match, setMatch] = React.useState(false);
  React.useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const m = window.matchMedia(query);
    const on = () => setMatch(m.matches);
    on();
    m.addEventListener ? m.addEventListener('change', on) : m.addListener(on);
    return () => (m.removeEventListener ? m.removeEventListener('change', on) : m.removeListener(on));
  }, [query]);
  return match;
}

export const useIsMobile = () => useMediaQuery('(max-width: 720px)');
