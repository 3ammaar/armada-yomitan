"""Touchscreen sessions."""

import math
import os
import select
import threading
import time

from armada_yomitan import strings
from armada_yomitan.capture import capture_png
from armada_yomitan.ocr.hit import find_hit_near
from armada_yomitan.ocr.image import ocr_frame, pixbuf_from_bytes
from armada_yomitan.ocr.rapid import LAST_TIMING
from armada_yomitan.ocr.regions import ocr_areas, ocr_region
from armada_yomitan.touch import map_touch, normalize, open_touch, touch_events, wait_for_tap


class ScreenSession:
    """Whole-screen scan mode."""

    def __init__(self, cfg, on_status, on_hit, on_state=None):
        self.cfg, self.on_status, self.on_hit, self.on_state = cfg, on_status, on_hit, on_state
        self.active = self.scanning = self.ready = False
        self.frame, self.lines, self.size, self.pending = None, [], (0, 0), None
        self._lock = threading.Lock()
        self._cancel_r, self._cancel_w = os.pipe()
        self._dev = self._info = self._thread = None

    def start(self):
        if self.active:
            return self.scan()
        dev = open_touch(self.cfg)
        dev.drain()
        if self.cfg.grab:
            try:
                dev.grab(True)
            except OSError:
                self.on_status(strings.TOUCH_GRAB_FAILED_TAPS)
        while select.select([self._cancel_r], [], [], 0)[0]:
            os.read(self._cancel_r, 64)
        self._dev, self._info, self.active = dev, dev.info, True
        self._thread = threading.Thread(target=self._touch_loop, daemon=True)
        self._thread.start()
        self.scan()

    def scan(self):
        with self._lock:
            if self.scanning:
                self.on_status(strings.STILL_READING_SCREEN)
                return
            self.scanning, self.ready = True, False
        self._state()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _state(self):
        if self.on_state:
            self.on_state(self.active, self.scanning, self.ready)

    def stop(self):
        if not self.active:
            return
        self.active = False
        os.write(self._cancel_w, b"x")
        if self._thread:
            self._thread.join(timeout=3)
        self._state()

    def _read(self, frame):
        return ocr_frame(frame, self.cfg)

    def _scan_worker(self):
        try:
            self.on_status(strings.CAPTURING_TOP_SCREEN)
            t0 = time.monotonic()
            frame = pixbuf_from_bytes(capture_png(self.cfg))
            size = (frame.get_width(), frame.get_height())
            self.on_status(strings.READING_TEXT_TAPS_QUEUED)
            t1 = time.monotonic()
            lines = self._read(frame)
            t2 = time.monotonic()
            with self._lock:
                self.frame, self.lines, self.size, self.ready = frame, lines, size, True
                pending, self.pending = self.pending, None
            parts = strings.SCAN_TIMING_GRAB.format(seconds=t1 - t0)
            if LAST_TIMING:
                parts += strings.SCAN_TIMING_ENGINE.format(detect=LAST_TIMING["detect"], read=LAST_TIMING["read"])
            self.on_status(strings.SCAN_READY.format(lines=len(lines), seconds=t2 - t0, detail=parts))
            if pending is not None and self.active:
                self._handle(pending)
        except Exception as e:
            self.on_status(strings.SCAN_FAILED.format(error=e))
        finally:
            with self._lock:
                self.scanning = False
            self._state()

    def _touch_loop(self):
        dev = self._dev
        try:
            while self.active:
                raw = wait_for_tap(dev, self._cancel_r, 3600)
                if raw is not None and self.active:
                    self._on_raw(raw)
        finally:
            if self.cfg.grab:
                try:
                    dev.grab(False)
                except OSError:
                    pass
            dev.close()

    def _on_raw(self, raw):
        with self._lock:
            queued = not self.ready
            if queued:
                self.pending = raw
        if queued:
            self.on_status(strings.STILL_READING_TAP_QUEUED)
        else:
            self._handle(raw)

    def _handle(self, raw):
        with self._lock:
            frame, lines, (W, H) = self.frame, self.lines, self.size
        px, py = map_touch(*raw, self._info, self.cfg.rotation, W, H)
        try:
            self.on_hit(frame, px, py, find_hit_near(lines, px, py, self.cfg), lines)
        except Exception as e:
            self.on_status(strings.ERROR.format(error=e))


class TapSession:
    """Single-tap scan mode."""

    def __init__(self, cfg, on_status, on_hit, on_state=None):
        self.cfg, self.on_status, self.on_hit, self.on_state = cfg, on_status, on_hit, on_state
        self.active = self.scanning = self.ready = False
        self._lock = threading.Lock()
        self._cancel_r, self._cancel_w = os.pipe()

    def start(self):
        with self._lock:
            if self.scanning:
                busy, cancel = True, False
            elif self.active:
                busy, cancel = False, True
            else:
                busy, cancel = False, False
                self.active = True
        if busy:
            self.on_status(strings.STILL_READING_TEXT)
        elif cancel:
            os.write(self._cancel_w, b"x")
        else:
            self._state()
            threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        if self.active and not self.scanning:
            os.write(self._cancel_w, b"x")

    def _state(self):
        if self.on_state:
            self.on_state(self.active, self.scanning, self.ready)

    def _run(self):
        dev = None
        try:
            while select.select([self._cancel_r], [], [], 0)[0]:
                os.read(self._cancel_r, 64)
            dev = open_touch(self.cfg)
            dev.drain()
            if self.cfg.grab:
                try:
                    dev.grab(True)
                except OSError:
                    self.on_status(strings.TOUCH_GRAB_FAILED_TAP)
            self.on_status(strings.WAITING_FOR_TAP)
            raw = wait_for_tap(dev, self._cancel_r, self.cfg.wait_seconds)
            if self.cfg.grab:
                try:
                    dev.grab(False)
                except OSError:
                    pass
            if raw is None:
                self.on_status(strings.CANCELLED_OR_TIMED_OUT)
                return
            self.scanning = True
            self._state()
            self.on_status(strings.CAPTURING_TOP_SCREEN)
            frame = pixbuf_from_bytes(capture_png(self.cfg))
            px, py = map_touch(*raw, dev.info, self.cfg.rotation, frame.get_width(), frame.get_height())
            self.on_status(strings.READING_TEXT)
            lines = ocr_region(frame, px, py, self.cfg)
            hit = find_hit_near(lines, px, py, self.cfg)
            self.on_hit(frame, px, py, hit, lines)
            if hit:
                self.on_status(strings.TAP_READY)
        except Exception as e:
            self.on_status(strings.ERROR.format(error=e))
        finally:
            if dev:
                dev.close()
            with self._lock:
                self.active = self.scanning = False
            self._state()


class AreaSession(ScreenSession):
    """Manual-areas scan mode."""

    NO_AREAS = strings.NO_OCR_AREAS_HINT

    def __init__(self, cfg, on_status, on_hit, on_state=None, get_areas=None):
        super().__init__(cfg, on_status, on_hit, on_state)
        self.get_areas = get_areas or (lambda: [])

    def start(self):
        if not self.get_areas():
            self.on_status(self.NO_AREAS)
            return
        super().start()

    def _read(self, frame):
        areas = self.get_areas()
        if not areas:
            raise RuntimeError(self.NO_AREAS)
        return ocr_areas(frame, areas, self.cfg)


class DrawSession:
    """Marking the areas to scan on the top screen."""

    MAX_AREAS = 16
    MIN_W, MIN_H = 0.02, 0.03            # the smallest rectangle worth keeping (fractions of the screen)
    DRAG_PX = 30                         # a touch that moves less than this (in top-screen pixels) is a tap
    REF = (1920, 1080)

    def __init__(self, cfg, on_status, on_mirror, on_areas, areas):
        self.cfg, self.on_status, self.on_mirror, self.on_areas = cfg, on_status, on_mirror, on_areas
        self.areas = [list(a) for a in areas]
        self.active = False
        self._thread = None
        self._cancel_r, self._cancel_w = os.pipe()

    def start(self):
        if self.active:
            return
        dev = open_touch(self.cfg)
        dev.drain()
        if self.cfg.grab:
            try:
                dev.grab(True)
            except OSError:
                self.on_status(strings.TOUCH_GRAB_FAILED_DRAWING)
        while select.select([self._cancel_r], [], [], 0)[0]:
            os.read(self._cancel_r, 64)
        self.active = True
        self._thread = threading.Thread(target=self._run, args=(dev,), daemon=True)
        self._thread.start()
        self.refresh()

    def stop(self):
        if self.active:
            self.active = False
            os.write(self._cancel_w, b"x")
            if self._thread:
                self._thread.join(timeout=3)
        return [list(a) for a in self.areas]

    def refresh(self):
        threading.Thread(target=self._mirror, daemon=True).start()

    def clear(self):
        self.areas = []
        self.on_areas(self.areas, None)
        self.on_status(strings.DRAW_ALL_DELETED)

    def _mirror(self):
        try:
            self.on_status(strings.CAPTURING_TOP_SCREEN)
            self.on_mirror(pixbuf_from_bytes(capture_png(self.cfg)))
            self.on_status(strings.DRAW_START)
        except Exception as e:
            self.on_status(strings.DRAW_CAPTURE_FAILED.format(error=e))

    @staticmethod
    def _rect(a, b):
        return [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]

    def _add(self, rect):
        if rect[2] - rect[0] < self.MIN_W or rect[3] - rect[1] < self.MIN_H:
            self.on_status(strings.DRAW_TOO_SMALL)
        elif len(self.areas) >= self.MAX_AREAS:
            self.on_status(strings.DRAW_MAXIMUM.format(maximum=self.MAX_AREAS))
        else:
            self.areas.append([round(v, 4) for v in rect])
            self.on_status(strings.by_count(len(self.areas), strings.DRAW_COUNT_ONE, strings.DRAW_COUNT_MANY).format(count=len(self.areas)))
        self.on_areas(self.areas, None)

    def _delete_at(self, u, v):
        for i in range(len(self.areas) - 1, -1, -1):
            a = self.areas[i]
            if a[0] <= u <= a[2] and a[1] <= v <= a[3]:
                del self.areas[i]
                self.on_status(strings.DRAW_DELETED)
                break
        else:
            self.on_status(strings.DRAW_HINT)
        self.on_areas(self.areas, None)

    def _run(self, dev):
        start, dragging = None, False
        try:
            for kind, rx, ry in touch_events(dev, self._cancel_r):
                u, v = normalize(rx, ry, dev.info, self.cfg.rotation)
                if kind == "down":
                    start, dragging = (u, v), False
                elif start is None:
                    continue
                elif kind == "move":
                    if not dragging and math.hypot((u - start[0]) * self.REF[0], (v - start[1]) * self.REF[1]) > self.DRAG_PX:
                        dragging = True
                    if dragging:
                        self.on_areas(self.areas, self._rect(start, (u, v)))
                else:
                    if dragging:
                        self._add(self._rect(start, (u, v)))
                    else:
                        self._delete_at(start[0], start[1])
                    start, dragging = None, False
        except Exception as e:
            self.on_status(strings.ERROR.format(error=e))
        finally:
            if self.cfg.grab:
                try:
                    dev.grab(False)
                except OSError:
                    pass
            dev.close()
            self.active = False
