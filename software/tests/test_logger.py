import os


def test_build_run_paths(tmp_path):
    from software.utils.logger import CsvLogger

    run_dir, run_name = CsvLogger.build_run_paths(str(tmp_path), "volt_log_20260525_174937")

    assert run_dir == os.path.join(str(tmp_path), "volt_log_20260525_174937")
    assert run_name == "volt_log_20260525_174937.csv"
