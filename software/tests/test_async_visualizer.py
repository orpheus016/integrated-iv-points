from unittest.mock import MagicMock

import pytest


def _patch_matplotlib(monkeypatch):
    import matplotlib.pyplot as plt

    fig = MagicMock()
    canvas = MagicMock()
    fig.canvas = canvas
    ax = MagicMock()
    ax.yaxis = MagicMock()
    ax.yaxis.set_major_formatter = MagicMock()
    ax.ticklabel_format = MagicMock()
    # make plot return a single-line sequence as matplotlib does
    ax.plot = lambda *a, **k: (MagicMock(),)
    ax.text = lambda *a, **k: MagicMock()

    monkeypatch.setattr(plt, "ion", lambda: None)
    monkeypatch.setattr(plt, "ioff", lambda: None)
    monkeypatch.setattr(plt, "show", lambda *args, **kwargs: None)
    monkeypatch.setattr(plt, "pause", lambda *args, **kwargs: None)
    monkeypatch.setattr(plt, "close", lambda *args, **kwargs: None)
    monkeypatch.setattr(plt, "subplots", lambda: (fig, ax))

    return fig, ax


def test_async_visualizer_updates_live_plot(monkeypatch):
    # Patch matplotlib before importing AsyncVisualizer to avoid GUI operations
    fig, ax = _patch_matplotlib(monkeypatch)

    from software.utils.visualization import AsyncVisualizer

    vis = AsyncVisualizer(window_seconds=1.0, max_samples=10, update_hz=0.0)

    for i in range(3):
        vis.submit_update(i * 0.1, 0.01 * i, None, None, None, None, False)

    vis.close()

    assert fig.canvas.draw_idle.called or fig.canvas.flush_events.called


def test_save_final_comparison_image_writes_file(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    output_path = tmp_path / "final.png"
    fig = MagicMock()
    ax = MagicMock()
    ax.yaxis = MagicMock()
    ax.yaxis.set_major_formatter = MagicMock()
    ax.ticklabel_format = MagicMock()

    monkeypatch.setattr(plt, "subplots", lambda: (fig, ax))
    monkeypatch.setattr(plt, "savefig", lambda path: output_path.write_bytes(b"plot"))
    monkeypatch.setattr(plt, "close", lambda *args, **kwargs: None)

    from software.utils.visualization import save_final_comparison_image

    saved = save_final_comparison_image(output_path, window_seconds=1.0, snapshot_v=0.1, true_v=None)

    assert saved
    assert output_path.exists()
    assert ax.ticklabel_format.called


def test_live_plot_applies_axis_formatting(monkeypatch):
    _, ax = _patch_matplotlib(monkeypatch)

    from software.utils.visualization import LivePlot

    LivePlot(window_seconds=1.0, max_samples=5, plot_mode="comparison")

    assert ax.ticklabel_format.called