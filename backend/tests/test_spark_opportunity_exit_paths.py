import importlib
from pathlib import Path


def _reload_exit_service():
    import backend.app.core.config as config
    import backend.app.services.spark_opportunity_exit as exit_service

    importlib.reload(config)
    return importlib.reload(exit_service)


def test_spark_exit_model_root_prefers_env(monkeypatch, tmp_path):
    exit_service = _reload_exit_service()

    model_root = tmp_path / "postclose_exit_v0_2"
    model_root.mkdir(parents=True, exist_ok=True)
    (model_root / "summary.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("SPARK_OPPORTUNITY_EXIT_MODEL_ROOT", str(model_root))

    resolved = exit_service._resolve_model_root(exit_service.PRIMARY_TRACK)
    assert resolved == model_root


def test_spark_exit_default_model_root_prefers_selection_artifacts():
    exit_service = _reload_exit_service()

    resolved = exit_service._resolve_model_root(exit_service.PRIMARY_TRACK)
    selection_artifacts_root = Path(exit_service.SELECTION_ARTIFACTS_ROOT).resolve()
    assert str(resolved.resolve()).startswith(str(selection_artifacts_root))
