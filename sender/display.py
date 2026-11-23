from __future__ import annotations

import queue
import threading
from functools import lru_cache
from time import perf_counter
from typing import Callable, Iterable, Optional

from .config import QR_ECC
from .playback import next_frame_deadline, parse_numbers
from .protocol import META, parse_packet


def show_animated_qr(packet_stream: Iterable[bytes], title: str, fps: float,
                     status_lines: Optional[Callable[[], list[str]]] = None,
                     cycle_frames: int = 0, encoder: str = "auto",
                     source_count: int = 0, block_size: int = 64,
                     stream_factory=None, *, ecc: str = QR_ECC) -> None:
    """Preview and replay original frames by stable source number."""
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError as exc:
        raise RuntimeError("Animated display requires Tkinter and Pillow") from exc
    from .qr import packet_to_image

    root = tk.Tk()
    root.title(title)
    root.configure(bg="white")
    root.resizable(True, True)
    root.geometry(f"{min(960, root.winfo_screenwidth() - 80)}x{min(950, root.winfo_screenheight() - 80)}")
    root.minsize(480, 540)
    area = tk.Frame(root, bg="white")
    area.pack(fill="both", expand=True, padx=12, pady=(12, 0))
    qr_label = tk.Label(area, bg="white")
    qr_label.place(relx=0.5, rely=0.5, anchor="center")
    text = tk.Label(root, justify="left", anchor="w", bg="white", fg="#202124", font=("Segoe UI", 10))
    text.pack(fill="x", padx=18)
    controls = tk.Frame(root, bg="white")
    controls.pack(fill="x", padx=18, pady=6)
    play_button = tk.Button(controls, text="播放", name="play")
    play_button.grid(row=0, column=0)
    entry = tk.Entry(controls, width=24, name="numbers")
    entry.insert(0, "0")
    entry.grid(row=0, column=1, padx=8)
    seek_button = tk.Button(controls, text="从编号播放", name="seek")
    seek_button.grid(row=0, column=2)
    repair_button = tk.Button(controls, text="仅补发列表", name="repair")
    repair_button.grid(row=0, column=3, padx=6)
    hint = tk.Label(root, text=f"0 = 文件信息；1～{source_count} = 原始分片。列表示例：0,12,35-38",
                    bg="white", anchor="w", fg="#334155")
    hint.pack(fill="x", padx=18, pady=(0, 12))
    if stream_factory is None:
        seek_button.configure(state="disabled")
        repair_button.configure(state="disabled")
    frames: queue.Queue = queue.Queue(maxsize=3)
    stopped = threading.Event()
    errors = []
    lock = threading.Lock()
    request = {"generation": 0, "stream": packet_stream}
    state = {"playing": False, "generation": 0, "done": False, "mode": "正常播放", "label": "准备文件信息帧…",
             "shown": 0, "segment_shown": 0, "started": None, "next_due": 0.0}
    image_ref = {"value": None, "base": None, "size": None}

    @lru_cache(maxsize=128)
    def encode(packet):
        return packet_to_image(packet, box_size=1, encoder=encoder, ecc=ecc).convert("L")

    def produce():
        generation = -1
        iterator = iter(())
        pending = None
        while not stopped.is_set():
            with lock:
                if generation != request["generation"]:
                    generation = request["generation"]
                    iterator = iter(request["stream"])
                    pending = None
            if pending is None:
                try:
                    packet = next(iterator)
                    kind, _, value = parse_packet(packet)
                    label = "编号 0 · 文件信息帧 META" if kind == META else (
                        f"编号 {value.block_id * block_size + value.symbol_index + 1} · 原始分片 B{value.block_id}/S{value.symbol_index}")
                    pending = (generation, label, encode(packet), False)
                except StopIteration:
                    pending = (generation, "播放结束", None, True)
                except Exception as exc:
                    errors.append(exc)
                    pending = (generation, f"生成失败：{exc}", None, True)
            try:
                frames.put(pending, timeout=0.05)
                is_done = pending[3]
                pending = None
                if is_done:
                    # Wait for a new playback request, rather than sending end markers repeatedly.
                    while not stopped.wait(0.05):
                        with lock:
                            if generation != request["generation"]:
                                break
            except queue.Full:
                pass

    def close(_event=None):
        stopped.set()
        root.destroy()

    def fit_image(_event=None):
        base = image_ref["base"]
        if base is None or stopped.is_set():
            return
        target = max(1, min(area.winfo_width(), area.winfo_height()) - 16)
        side = base.width * max(1, target // base.width)
        if image_ref["size"] == side and _event is not None:
            return
        image_ref["size"] = side
        image_ref["value"] = ImageTk.PhotoImage(base.resize((side, side), Image.Resampling.NEAREST))
        qr_label.configure(image=image_ref["value"])

    def toggle():
        if state["done"]:
            return
        state["playing"] = not state["playing"]
        state["started"] = None
        state["segment_shown"] = 0
        state["next_due"] = perf_counter()
        play_button.configure(text="暂停" if state["playing"] else "播放")

    def replace_stream(new_stream):
        state["generation"] += 1
        with lock:
            request.update(generation=state["generation"], stream=new_stream)
        state.update(playing=True, done=False, label="准备文件信息帧…",
                     started=None, segment_shown=0, shown=0, next_due=perf_counter())
        image_ref["base"] = None
        qr_label.configure(image="")
        play_button.configure(text="暂停")

    def change_mode(selected):
        try:
            numbers = parse_numbers(entry.get(), source_count)
            if not selected and len(numbers) != 1:
                raise ValueError("从编号播放时只输入一个编号；多个编号请点“仅补发列表”")
            start_number = None if selected else numbers[0]
            new_stream = stream_factory(start_number, numbers if selected else None)
        except ValueError as exc:
            hint.configure(text=str(exc), fg="#b91c1c")
            return
        state["mode"] = "仅补发：" + entry.get() if selected else f"从编号 {start_number} 播放"
        replace_stream(new_stream)
        hint.configure(text="沿用当前任务；手机保留接收进度。0 是文件信息帧。", fg="#334155")

    play_button.configure(command=toggle)
    seek_button.configure(command=lambda: change_mode(False))
    repair_button.configure(command=lambda: change_mode(True))
    area.bind("<Configure>", fit_image)
    root.bind("<Escape>", close)
    root.protocol("WM_DELETE_WINDOW", close)
    threading.Thread(target=produce, daemon=True).start()
    interval = 1.0 / max(1.0, fps)

    def tick():
        if stopped.is_set():
            return
        now = perf_counter()
        if image_ref["base"] is None or (state["playing"] and now >= state["next_due"]):
            while True:
                try:
                    generation, label, image, done = frames.get_nowait()
                except queue.Empty:
                    break
                if generation != state["generation"]:
                    continue
                state["label"] = label
                if done:
                    state.update(done=True, playing=False)
                    play_button.configure(text="播放结束")
                else:
                    image_ref["base"] = image
                    fit_image()
                    state["shown"] += 1
                    if state["playing"]:
                        state["segment_shown"] += 1
                        if state["started"] is None:
                            state["started"] = now
                    state["next_due"] = next_frame_deadline(state["next_due"], perf_counter(), interval)
                break
        actual = max(0, state["segment_shown"] - 1) / max(0.001, now - state["started"]) if state["started"] is not None else 0
        lines = list(status_lines() if status_lines else [])
        if cycle_frames:
            lines.append(f"Normal cycle: {cycle_frames:,} QR codes; shown {state['shown']:,}")
        lines.extend([state["label"], f"{state['mode']} · {'播放中' if state['playing'] else '已暂停'}",
                      f"Actual: {actual:.1f} FPS / target {fps:g} FPS · ESC: 关闭"])
        text.configure(text="\n".join(lines))
        root.after(5, tick)

    root.after(0, tick)
    root.mainloop()
    if errors:
        raise RuntimeError(f"QR frame generation failed: {errors[0]}") from errors[0]
