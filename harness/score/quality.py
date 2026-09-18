"""Агрегация Q и мост «скорер издания → ось конституции».

Слой скоринга, не загрузки: здесь живёт формула качества (mean_of_applicable
по конституции) и маппинг имён скореров на буквы осей. Загрузчики (loaders.py)
остаются чистыми «схема + load_*» — расчёта в них нет.

Самопроверка:  python3 -m harness.score.quality
"""

from __future__ import annotations

from harness.loaders import Constitution, load_constitution

# Имя скорера в издании → буква оси конституции
SCORER_TO_AXIS = {"syntax": "S", "meaning": "M", "optimization": "O", "platform": "P"}


def compute_q(
    scores: dict[str, int | None], category: str, constitution: Constitution
) -> float | None:
    """Q = среднее по ПРИМЕНИМЫМ осям (formula: mean_of_applicable).

    scores: {ось: балл | None}. None = ось не измерена (нет инструмента) —
    исключается из среднего, как и неприменимые к категории (см. гейтинг L1).
    """
    assert constitution.q_formula == "mean_of_applicable", constitution.q_formula
    applicable = constitution.applicable_axes(category)
    measured = [scores[a] for a in applicable if scores.get(a) is not None]
    if not measured:
        return None
    return round(sum(measured) / len(measured), 2)


def coverage(
    scores: dict[str, int | None], category: str, constitution: Constitution
) -> tuple[int, int]:
    """Сколько осей реально измерено из применимых к категории: (измерено, применимо).

    Зачем отдельным числом. Q усредняет только измеренные оси, поэтому выпадение оси
    его ПОДНИМАЕТ: запись с S=8 и M=0 даёт 4.0, если O и P не измерены, против 2.67
    при четырёх осях. Сравнивать такую запись с полностью измеренной по одному Q
    нельзя — сравниваются разные вещи. Охват держит это различие на виду вместо того,
    чтобы прятать его подставным нулём в неизмеренную ось.
    """
    applicable = constitution.applicable_axes(category)
    return sum(1 for a in applicable if scores.get(a) is not None), len(applicable)


def main() -> None:
    const = load_constitution()
    demo = compute_q({"S": 10, "M": 8, "O": 6, "P": None}, "A", const)
    print(f"проба Q (кат. A, S=10 M=8 O=6, P=N/A): {demo}  (ожидаем 8.0)")
    print(f"охват: {coverage({'S': 10, 'M': 8, 'O': 6, 'P': None}, 'A', const)}")


if __name__ == "__main__":
    main()
