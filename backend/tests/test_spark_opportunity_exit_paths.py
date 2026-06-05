from pathlib import Path


def test_spark_exit_model_root_prefers_env(monkeypatch, tmp_path):
    import backend.app.services.spark_opportunity_exit as exit_service

    model_root = tmp_path / "postclose_exit_v0_2"
    model_root.mkdir(parents=True, exist_ok=True)
    (model_root / "summary.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("SPARK_OPPORTUNITY_EXIT_MODEL_ROOT", str(model_root))

    resolved = exit_service._resolve_model_root(exit_service.PRIMARY_TRACK)
    assert resolved == model_root


def test_spark_exit_default_model_root_stays_inside_repo():
    import backend.app.services.spark_opportunity_exit as exit_service

    resolved = exit_service._resolve_model_root(exit_service.PRIMARY_TRACK)
    root = Path(exit_service.ROOT).resolve()
    assert str(resolved.resolve()).startswith(str(root))

