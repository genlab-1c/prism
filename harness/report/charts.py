"""Генерация графиков лидерборда (publication-quality, matplotlib) из оценок L1.

Отдельный шаг `prism charts`: читает results/auto/*_auto_l1.json (те же данные, что
`prism leaderboard`/`docs`) и рендерит SVG + PNG в каталог (по умолчанию results/charts/):
  · q_ranking_<cat>   — ранжир моделей по Q̄ (горизонтальные бары)
  · smop_bars_<cat>   — сравнение по осям S·M·O·(P) для топ-N моделей
  · smop_radar_<cat>  — радар-профиль SMOP топ-N моделей

matplotlib — опциональная зависимость (группа charts): `uv sync --group charts`.
Нет matplotlib → команда честно об этом сообщает, а не падает трейсбеком.
"""

from __future__ import annotations

from pathlib import Path

from .leaderboard_md import PRISM, _load, _ranked

# оси SMOP → фирменные цвета (как на сайте)
AXIS_COLORS = {"S": "#7c7ef8", "M": "#22d3ee", "O": "#34d399", "P": "#fbbf24", "Q": "#eef2f8"}
CAT_AXES = {"A": ["S", "M", "O"], "B": ["S", "M", "O", "P"]}
CAT_TITLE = {"A": "категория A · алгоритмика", "B": "категория B · платформа 1С"}

# палитра для моделей на радаре (различимая, дружелюбная к печати)
MODEL_PALETTE = [
    "#22d3ee",
    "#34d399",
    "#fbbf24",
    "#f472b6",
    "#7c7ef8",
    "#fb923c",
    "#4ade80",
    "#e879f9",
]

_STYLE = {
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "axes.edgecolor": "#3a4a63",
    "axes.labelcolor": "#1a2230",
    "text.color": "#1a2230",
    "xtick.color": "#3a4a63",
    "ytick.color": "#3a4a63",
    "figure.titlesize": 14,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
}


def check_matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401

        return True
    except ImportError:
        return False


def _q_color(q: float | None) -> str:
    if q is None:
        return "#c2c9d6"
    return "#34d399" if q >= 7 else "#fbbf24" if q >= 4 else "#f87171"


def _save(fig, out_dir: Path, name: str) -> list[Path]:
    import matplotlib.pyplot as plt

    paths = []
    for fmt in ("svg", "png"):
        p = out_dir / f"{name}.{fmt}"
        fig.savefig(p, format=fmt)
        paths.append(p)
    plt.close(fig)
    return paths


def _plot_q_ranking(cat: str, rank: list, out_dir: Path) -> list[Path]:
    """Горизонтальные бары Q̄ по моделям (сверху — лучший)."""
    import matplotlib.pyplot as plt

    rows = [(n, m["Q"]) for n, m, _ in rank if m.get("Q") is not None]
    rows.reverse()  # matplotlib рисует barh снизу вверх
    names = [n for n, _ in rows]
    vals = [v for _, v in rows]
    fig, ax = plt.subplots(figsize=(9, max(3.5, len(names) * 0.42)))
    bars = ax.barh(names, vals, color=[_q_color(v) for v in vals])
    for b, v in zip(bars, vals, strict=True):
        ax.text(
            v + 0.12,
            b.get_y() + b.get_height() / 2,
            f"{v:.2f}",
            va="center",
            fontsize=9,
            color="#1a2230",
        )
    ax.set_xlim(0, 10.6)
    ax.set_xlabel("Q̄ · общий балл (0–10)")
    ax.set_title(f"Лидерборд PRISM — {CAT_TITLE[cat]}", fontweight="bold")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _save(fig, out_dir, f"q_ranking_{cat}")


def _plot_smop_bars(cat: str, rank: list, out_dir: Path, top: int) -> list[Path]:
    """Сгруппированные бары по осям S·M·O·(P) для топ-N моделей."""
    import matplotlib.pyplot as plt
    import numpy as np

    axes = CAT_AXES[cat]
    sel = [(n, m) for n, m, _ in rank[:top]]
    names = [n for n, _ in sel]
    y = np.arange(len(names))
    h = 0.8 / len(axes)
    fig, ax = plt.subplots(figsize=(9, max(3.5, len(names) * 0.9)))
    for i, a in enumerate(axes):
        vals = [(m.get(a) or 0) for _, m in sel]
        off = (i - (len(axes) - 1) / 2) * h
        ax.barh(y + off, vals, h, label=a, color=AXIS_COLORS[a])
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlim(0, 10.6)
    ax.set_xlabel("балл по оси (0–10)")
    ax.set_title(f"Профиль по осям SMOP — {CAT_TITLE[cat]} (топ-{len(names)})", fontweight="bold")
    ax.legend(ncol=len(axes), loc="lower right", frameon=False)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _save(fig, out_dir, f"smop_bars_{cat}")


def _plot_radar(cat: str, rank: list, out_dir: Path, top: int) -> list[Path]:
    """Радар-профиль SMOP для топ-N моделей."""
    import matplotlib.pyplot as plt
    import numpy as np

    axes = CAT_AXES[cat]
    ang = np.linspace(0, 2 * np.pi, len(axes), endpoint=False).tolist()
    ang += ang[:1]
    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    for idx, (n, m, _) in enumerate(rank[:top]):
        vals = [(m.get(a) or 0) for a in axes]
        vals += vals[:1]
        c = MODEL_PALETTE[idx % len(MODEL_PALETTE)]
        ax.plot(ang, vals, "o-", linewidth=1.8, label=n, color=c)
        ax.fill(ang, vals, alpha=0.08, color=c)
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels(axes, size=12, fontweight="bold")
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], size=8)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9, frameon=False)
    ax.set_title(f"Профиль SMOP — {CAT_TITLE[cat]} (топ-{top})", size=13, fontweight="bold", pad=24)
    return _save(fig, out_dir, f"smop_radar_{cat}")


def generate(out_dir: Path | str = None, top: int = 8) -> list[Path]:
    """Отрисовать все графики по свежим оценкам L1. Вернуть список файлов."""
    import matplotlib

    matplotlib.use("Agg")  # без GUI
    import matplotlib.pyplot as plt

    plt.rcParams.update(_STYLE)

    out = Path(out_dir) if out_dir else PRISM / "results" / "charts"
    out.mkdir(parents=True, exist_ok=True)

    made: list[Path] = []
    for cat in ("A", "B"):
        res = _load(cat)
        if not res:
            continue
        rank = _ranked(res)
        if not rank:
            continue
        made += _plot_q_ranking(cat, rank, out)
        made += _plot_smop_bars(cat, rank, out, top)
        made += _plot_radar(cat, rank, out, top)
    return made
