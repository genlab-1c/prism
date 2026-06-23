"""Упаковка/приём результата (prism submit) — отпечаток совместимости и round-trip."""

from __future__ import annotations

import json

from harness import submit


def _auto_result() -> dict:
    """Минимальная авто-оценка L1 в формате results/auto/*.json."""
    return {
        "experiment_id": "experiment_A_20260101_000000",
        "evaluator_id": "auto_l1",
        "edition": "core",
        "runner": "local",
        "syntax_analyzer": "bsl-ls 0.29.0",
        "protocol_version": "1.1.0",
        "constitution_version": "1.0.0",
        "tasks": [
            {"task_id": "A1", "model_id": "ds/x", "model_name": "DeepSeek", "runs": []},
            {"task_id": "A1", "model_id": "g/x", "model_name": "Gemini", "runs": []},
        ],
    }


def test_fingerprint_is_stable_and_hex():
    fp1 = submit.benchmark_fingerprint()
    fp2 = submit.benchmark_fingerprint()
    assert fp1 == fp2  # детерминирован
    assert len(fp1) == 64 and all(c in "0123456789abcdef" for c in fp1)


def test_build_then_verify_roundtrip_compatible(tmp_path, monkeypatch):
    monkeypatch.setattr(submit, "PRISM", tmp_path)  # изоляция записи от реального results/
    auto = tmp_path / "auto.json"
    auto.write_text(json.dumps(_auto_result()), encoding="utf-8")

    out, sub = submit.build_submission(auto, created="2026-01-01T00:00:00")
    assert out.exists()
    assert sub["compat_hash"] == submit.benchmark_fingerprint()
    assert sub["models"] == ["DeepSeek", "Gemini"]
    assert sub["versions"]["protocol"] == "1.1.0"

    info = submit.verify_submission(out)
    assert info["compatible"] is True


def test_verify_detects_other_version(tmp_path, monkeypatch):
    monkeypatch.setattr(submit, "PRISM", tmp_path)
    auto = tmp_path / "auto.json"
    auto.write_text(json.dumps(_auto_result()), encoding="utf-8")
    out, _ = submit.build_submission(auto)

    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["compat_hash"] = "0" * 64  # как будто прогон на другой версии бенчмарка
    out.write_text(json.dumps(doc), encoding="utf-8")

    info = submit.verify_submission(out)
    assert info["compatible"] is False


def test_apply_writes_into_results_auto(tmp_path, monkeypatch):
    monkeypatch.setattr(submit, "PRISM", tmp_path)
    auto = tmp_path / "auto.json"
    auto.write_text(json.dumps(_auto_result()), encoding="utf-8")
    _, sub = submit.build_submission(auto)

    dest = submit.apply_submission(sub)
    assert dest == tmp_path / "results" / "auto" / "experiment_A_20260101_000000_auto_l1.json"
    assert (
        json.loads(dest.read_text(encoding="utf-8"))["experiment_id"]
        == "experiment_A_20260101_000000"
    )
