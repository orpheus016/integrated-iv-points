from __future__ import annotations


def test_main_logs_gain_adjusted_resistance(tmp_path, monkeypatch):
    from software.config.config import SimulationConfig
    import software.main as main_module

    class Args:
        source = "dummy"
        backbone = "baseline"
        csv_path = ""
        plot_backend = ""
        live_plot = False
        live_backbones = ""
        live_duration = 0.0
        plot_mode = "comparison"
        plot_update_hz = 0.0
        save_plot_on_interrupt = False
        stop_on_snapshot = True
        stop_holdoff_s = 0.0
        stop_require_post_switch = False
        stop_final_holdoff_s = 0.0
        output_dir = str(tmp_path)

    class FakeParser:
        def parse_args(self):
            return Args()

    def fake_build_simulation_config(_args):
        return SimulationConfig(
            sample_rate_hz=10.0,
            window_seconds=1.0,
            snapshot_min_recording_s=0.1,
            max_measurement_s=1.0,
            snapshot_window_s=0.2,
            snapshot_std_threshold_v=0.01,
            snapshot_min_duration_s=0.1,
            gain=2.0,
        )

    def fake_source_iterator(_args, _sim_config):
        return iter([
            (0.0, 0.2, 10.0),
            (0.1, 0.2, 10.0),
            (0.2, 0.2, 10.0),
        ])

    monkeypatch.setattr(main_module, "build_arg_parser", lambda: FakeParser())
    monkeypatch.setattr(main_module, "build_simulation_config", fake_build_simulation_config)
    monkeypatch.setattr(main_module, "build_source_iterator", fake_source_iterator)

    main_module.main()

    csv_files = list(tmp_path.rglob("*.csv"))
    assert csv_files
    contents = csv_files[0].read_text(encoding="utf-8").splitlines()
    assert len(contents) >= 2
    assert ",10.00000000," in contents[1]