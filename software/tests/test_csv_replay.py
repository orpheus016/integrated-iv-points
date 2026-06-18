import csv


def test_csv_logged_reader_parses_logger_csv(tmp_path):
    from software.utils.csv_replay import csv_logged_reader

    csv_path = tmp_path / "log.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "elapsed_s", "measured_v", "current_mA", "resistance", "std_dev", "stage"])
        writer.writerow(["2024-01-01T00:00:00.000", "0.000000", "0.00100000", "10.00000000", "", "", ""])
        writer.writerow(["2024-01-01T00:00:00.100", "0.100000", "0.00150000", "10.00000000", "", "", ""])

    samples = list(csv_logged_reader(str(csv_path)))

    assert samples == [
        (0.0, 0.001, 10.0),
        (0.1, 0.0015, 10.0),
    ]
