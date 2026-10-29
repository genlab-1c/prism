import React from 'react';
import edition from '../../data/prism1.json';
import { Icon } from '../chrome/Chrome.jsx';
import { Chronicle } from './Chronicle.jsx';
import '../../styles/edition-notice.css';

const number = new Intl.NumberFormat('ru-RU');
const fixedAt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
}).format(new Date(`${edition.fixedAt}T00:00:00Z`)).replace(/ г\.$/, '');

export function EditionNotice({ models }) {
  const [expanded, setExpanded] = React.useState(false);
  return (
    <section className="edition-notice" aria-labelledby="edition-notice-title">
      <div className="edition-notice__heading">
        <h2 id="edition-notice-title">{edition.name} завершён. Готовим следующий выпуск</h2>
        <time dateTime={edition.fixedAt}>{fixedAt}</time>
      </div>
      <p className="edition-notice__totals">
        {number.format(edition.tasks)} задач · {number.format(edition.models)} моделей · {number.format(edition.generations)} генераций
      </p>
      <p className="edition-notice__description">
        Текущие задачи всё слабее различают сильные модели. Фиксируем результаты первого выпуска
        и готовим более сложный банк. Все результаты и решения остаются доступны.
      </p>
      <div className="edition-notice__actions">
        <a className="edition-notice__link edition-notice__rss" href={`${import.meta.env.BASE_URL}feed.xml`} target="_blank" rel="noopener noreferrer">
          <Icon name="rss" size={14} /> Следить за выпуском · RSS
        </a>
        <button className="edition-notice__toggle" type="button" aria-expanded={expanded}
          aria-controls="edition-notice-evidence" onClick={() => setExpanded(!expanded)}>
          Почему фиксируем банк
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {edition.feedbackUrl && (
          <a className="edition-notice__link edition-notice__feedback" href={edition.feedbackUrl} target="_blank" rel="noopener noreferrer">
            Поделиться опытом и идеями
          </a>
        )}
      </div>
      <div className="edition-notice__evidence" id="edition-notice-evidence" hidden={!expanded}>
        <Chronicle models={models} />
      </div>
    </section>
  );
}
