from backend.app.services import selection_market_environment_gate as gate


def _write_market_state(path, rows):
    path.mkdir(parents=True, exist_ok=True)
    lines = [
        "trade_date,water_score,market_regime,market_detail,market_detail_label,default_action,all_up_ratio_5d,small_up_ratio_5d,all_med_ret_5d,csi1000_return_5d_pct,reason_top3",
    ]
    for row in rows:
        lines.append(
            ",".join(
                [
                    row["trade_date"],
                    str(row.get("water_score", 50)),
                    row.get("market_regime", "caution"),
                    row.get("market_detail", "caution"),
                    row.get("market_detail_label", "谨慎"),
                    row.get("default_action", "观察为主"),
                    str(row.get("all_up_ratio_5d", 50)),
                    str(row.get("small_up_ratio_5d", 50)),
                    str(row.get("all_med_ret_5d", 0)),
                    str(row.get("csi1000_return_5d_pct", 0)),
                    row.get("reason_top3", "样本"),
                ]
            )
        )
    (path / "market_state_daily.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_market_environment_prefers_runtime_dir_and_refreshes_on_file_change(monkeypatch, tmp_path):
    runtime_dir = tmp_path / "runtime_gate"
    repo_dir = tmp_path / "repo_gate"
    _write_market_state(repo_dir, [{"trade_date": "2026-06-10", "water_score": 10}])
    _write_market_state(runtime_dir, [{"trade_date": "2026-06-11", "water_score": 20}])
    monkeypatch.setenv("MARKET_ENVIRONMENT_GATE_DIR", str(runtime_dir))
    monkeypatch.setattr(gate, "REPO_RESEARCH_DIR", repo_dir)
    gate._read_csv_cached.cache_clear()

    env_11 = gate.get_market_environment("2026-06-11")

    assert env_11["available"] is True
    assert env_11["water_score"] == 20
    assert gate.get_market_environment("2026-06-10")["available"] is False

    _write_market_state(
        runtime_dir,
        [
            {"trade_date": "2026-06-11", "water_score": 20},
            {"trade_date": "2026-06-12", "water_score": 60, "market_regime": "attack", "market_detail_label": "攻击", "default_action": "可参与"},
        ],
    )

    env_12 = gate.get_market_environment("2026-06-12")

    assert env_12["available"] is True
    assert env_12["water_score"] == 60
    assert len(env_12["recent"]) == 2
