import pytest

from sender.playback import next_frame_deadline


def test_coarse_timer_keeps_twenty_fps_without_accumulating_delay():
    # A nominal 5 ms Tk timer wakes about every 16 ms on this Windows PC;
    # resizing/uploading a QR adds another 8 ms on the rendering callbacks.
    now = 0.0
    deadline = 0.0
    presented = []
    while now < 10:
        if now >= deadline:
            presented.append(now)
            now += 0.008
            deadline = next_frame_deadline(deadline, now, 0.05)
        now += 0.016
    fps = (len(presented) - 1) / (presented[-1] - presented[0])
    assert 19.8 <= fps <= 20.2


def test_long_stall_rebases_instead_of_bursting_or_skipping_packets():
    deadline = next_frame_deadline(1.0, 1.4, 0.05)
    assert deadline == pytest.approx(1.45)
    # Once playback resumes, ordinary late callbacks keep the fixed timeline.
    assert next_frame_deadline(deadline, 1.46, 0.05) == pytest.approx(1.5)
