import pytest

tk = pytest.importorskip("tkinter")

from sender.display import show_animated_qr
from sender.protocol import TransferMetadata, encode_meta, split_source_symbols


def test_window_can_resize_and_reports_cycle_progress(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("A desktop display is required for the window-resize integration test")
    monkeypatch.setattr(tk, "Tk", lambda: root)
    observed = []
    packet = encode_meta(TransferMetadata.new("display.zip", 42, 1200, 1, 64))

    def resize():
        root.geometry("500x600")
        root.update_idletasks()

    def inspect():
        area, text, controls, _hint = root.winfo_children()
        label = area.winfo_children()[0]
        image_name = str(label.cget("image"))
        observed.append({
            "fullscreen": root.attributes("-fullscreen"),
            "size": (root.winfo_width(), root.winfo_height()),
            "qr_width": int(root.tk.call("image", "width", image_name)),
            "space": min(area.winfo_width(), area.winfo_height()),
            "text": text.cget("text"),
            "play": controls.nametowidget("play").cget("text"),
        })

    root.after(250, resize)
    root.after(500, inspect)
    root.after(650, root.destroy)
    show_animated_qr(iter([packet] * 20), "QFS resize test", 20,
                     lambda: ["QR/cycle: 20"], cycle_frames=20)
    assert observed
    assert not observed[0]["fullscreen"]
    assert observed[0]["size"] == (500, 600)
    assert 0 < observed[0]["qr_width"] <= observed[0]["space"]
    assert "20 QR codes; shown 1" in observed[0]["text"]
    assert observed[0]["play"] == "播放"
    assert "Actual:" in observed[0]["text"]


def test_play_pause_and_seek_discard_old_queued_frames(monkeypatch):
    from sender.cli import _stream
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("A desktop display is required")
    monkeypatch.setattr(tk, "Tk", lambda: root)
    records = split_source_symbols(b"abcdefgh", 1, block_size=2)
    meta = TransferMetadata.new("seek.zip", 8, 1, len(records), 2)
    observed, callback_errors = [], []
    root.report_callback_exception = lambda *args: callback_errors.append(args)

    def control(name):
        return root.winfo_children()[2].nametowidget(name)

    def snapshot():
        observed.append(root.winfo_children()[1].cget("text"))

    def seek():
        entry = control("numbers")
        entry.delete(0, "end")
        entry.insert(0, "7")
        control("repair").invoke()

    root.after(200, lambda: control("play").invoke())
    root.after(420, lambda: control("play").invoke())
    root.after(480, snapshot)
    root.after(650, snapshot)
    root.after(700, seek)
    root.after(1050, snapshot)
    root.after(1200, root.destroy)
    show_animated_qr(_stream(meta, records, 24), "QFS controls test", 8,
                     source_count=len(records), block_size=2,
                     stream_factory=lambda start, selected: _stream(meta, records, 24, start, selected))
    assert not callback_errors
    assert observed[0].split("Actual:")[0] == observed[1].split("Actual:")[0]
    assert "仅补发：7" in observed[2]
    assert "编号 7" in observed[2] or "编号 0" in observed[2]
