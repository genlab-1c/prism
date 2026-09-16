"""Гигиена YAML: дублирующиеся ключи.

PyYAML (yaml.safe_load) молча берёт последнее значение из одинаковых ключей, поэтому дубль
проходит prism check и все питоновские тесты. А js-yaml в сборке витрины на нём падает, и
ломается уже деплой. Здесь дубли ловятся на этапе тестов, до коммита в main.
"""

from __future__ import annotations

import pytest
import yaml
from yaml.constructor import ConstructorError

from harness.loaders import PRISM

# каталоги, чьи YAML читают харнесс и сборка витрины
_DIRS = ("generation", "metrics", "editions", "tasks")
_FILES = sorted(p for d in _DIRS for p in (PRISM / d).rglob("*.y*ml"))


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader, который падает на повторяющемся ключе вместо тихой перезаписи."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ConstructorError(
                    None, None, f"дублирующийся ключ {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def test_loader_catches_duplicates():
    # страховка самой проверки: без неё сломанный загрузчик молча пропустил бы всё
    with pytest.raises(ConstructorError, match="дублирующийся ключ"):
        yaml.load("models:\n  a: 1\n  a: 2\n", Loader=_UniqueKeyLoader)  # noqa: S506 — наследник SafeLoader


def test_yaml_files_found():
    assert _FILES, "не нашли ни одного YAML — проверьте пути _DIRS"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: str(p.relative_to(PRISM)))
def test_no_duplicate_keys(path):
    with path.open(encoding="utf-8") as f:
        yaml.load(f, Loader=_UniqueKeyLoader)  # noqa: S506 — наследник SafeLoader
