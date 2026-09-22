"""Raw evdev touch input."""

import fcntl
import grp
import os
import re
import select
import struct
import time
from dataclasses import dataclass

from armada_yomitan import strings
from armada_yomitan.console import log_error

EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03


SYN_REPORT = 0x00


BTN_TOUCH = 0x14A


ABS_X, ABS_Y = 0x00, 0x01


ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x35, 0x36, 0x39


EVENT = struct.Struct("llHHi")  # struct input_event on 64-bit: timeval, type, code, value (24 bytes)


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("E") << 8) | nr


def EVIOCGABS(code):
    return _ioc(2, 0x40 + code, 24)  # _IOR('E', 0x40+abs, struct input_absinfo)


EVIOCGRAB = _ioc(1, 0x90, 4)  # _IOW('E', 0x90, int)


@dataclass
class AbsInfo:
    xcode: int
    ycode: int
    x_min: int
    x_max: int
    y_min: int
    y_max: int


def read_abs_info(fd):
    for xc, yc in ((ABS_MT_POSITION_X, ABS_MT_POSITION_Y), (ABS_X, ABS_Y)):
        try:
            x = struct.unpack("6i", fcntl.ioctl(fd, EVIOCGABS(xc), bytes(24)))
            y = struct.unpack("6i", fcntl.ioctl(fd, EVIOCGABS(yc), bytes(24)))
        except OSError:
            continue
        if x[2] > x[1] and y[2] > y[1]:
            return AbsInfo(xc, yc, x[1], x[2], y[1], y[2])
    return None


def list_input_devices():
    try:
        text = open("/proc/bus/input/devices").read()
    except OSError:
        return []
    devs = []
    for block in text.strip().split("\n\n"):
        name = re.search(r'N: Name="(.*)"', block)
        handlers = re.search(r"H: Handlers=(.*)", block)
        ev = re.search(r"\bevent(\d+)\b", handlers.group(1)) if handlers else None
        if name and ev:
            devs.append((name.group(1), "/dev/input/event" + ev.group(1)))
    return devs


class TouchDevice:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.info = read_abs_info(self.fd)
        if self.info is None:
            os.close(self.fd)
            raise RuntimeError(strings.TOUCH_NO_COORDINATES.format(path=path))

    def grab(self, on):
        fcntl.ioctl(self.fd, EVIOCGRAB, 1 if on else 0)

    def drain(self):
        while True:
            try:
                if not os.read(self.fd, EVENT.size * 64):
                    return
            except BlockingIOError:
                return

    def close(self):
        os.close(self.fd)


def permission_details(path):
    parts = []
    try:
        st = os.stat(path)
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group = str(st.st_gid)
        parts.append(f"{path} is mode {st.st_mode & 0o777:04o}, group {group}")
    except OSError as e:
        parts.append(f"{path} can't even be inspected ({e})")
    names = []
    for gid in os.getgroups():
        try:
            names.append(grp.getgrgid(gid).gr_name)
        except KeyError:
            names.append(str(gid))
    parts.append(f"this process is uid {os.getuid()} with groups {', '.join(names) or 'none'}")
    return "; ".join(parts)


def open_touch(cfg):
    if not cfg.touch_name:
        raise RuntimeError(strings.TOUCH_NOT_CHOSEN)
    matches = [(n, p) for n, p in list_input_devices() if cfg.touch_name.lower() in n.lower()]
    if not matches:
        raise RuntimeError(strings.TOUCH_NO_DEVICE.format(name=cfg.touch_name))
    if len(matches) > 1:
        raise RuntimeError(strings.TOUCH_SEVERAL_DEVICES.format(devices=", ".join(f"{n} ({p})" for n, p in matches)))
    try:
        return TouchDevice(matches[0][1])
    except PermissionError:
        log_error("Why the touchscreen can't be read: " + permission_details(matches[0][1]))
        raise RuntimeError(strings.TOUCH_NO_PERMISSION.format(path=matches[0][1]))


def wait_for_tap(dev, cancel_fd, timeout):
    info = dev.info
    deadline = time.monotonic() + timeout
    x = y = None
    contact = False
    tap = None
    buf = b""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return tap  # None if no tap yet; the tap itself if the finger never reported lifting
        ready, _, _ = select.select([dev.fd, cancel_fd], [], [], remaining)
        if cancel_fd in ready:
            return None
        if dev.fd not in ready:
            continue
        try:
            buf += os.read(dev.fd, EVENT.size * 64)
        except BlockingIOError:
            continue
        while len(buf) >= EVENT.size:
            _, _, etype, code, value = EVENT.unpack_from(buf)
            buf = buf[EVENT.size:]
            if etype == EV_ABS:
                if code == info.xcode:
                    x = value
                elif code == info.ycode:
                    y = value
                elif code == ABS_MT_TRACKING_ID:
                    contact = value >= 0
            elif etype == EV_KEY and code == BTN_TOUCH:
                contact = value == 1
            elif etype == EV_SYN and code == SYN_REPORT:
                if tap is None:
                    if contact and x is not None and y is not None:
                        tap = (x, y)
                        deadline = min(deadline, time.monotonic() + 1.5)
                elif not contact:
                    return tap


def normalize(rx, ry, info, rotation):
    """Raw touch coordinates to (u, v) in 0..1 of the displayed image."""
    u = (rx - info.x_min) / max(1, info.x_max - info.x_min)
    v = (ry - info.y_min) / max(1, info.y_max - info.y_min)
    u, v = min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)
    if rotation == 90:
        u, v = 1 - v, u
    elif rotation == 180:
        u, v = 1 - u, 1 - v
    elif rotation == 270:
        u, v = v, 1 - u
    return u, v


def map_touch(rx, ry, info, rotation, out_w, out_h):
    u, v = normalize(rx, ry, info, rotation)
    return int(u * (out_w - 1)), int(v * (out_h - 1))


def touch_events(dev, cancel_fd):
    info = dev.info
    x = y = last = None
    contact = was = False
    buf = b""
    while True:
        ready, _, _ = select.select([dev.fd, cancel_fd], [], [])
        if cancel_fd in ready:
            return
        try:
            buf += os.read(dev.fd, EVENT.size * 64)
        except BlockingIOError:
            continue
        while len(buf) >= EVENT.size:
            _, _, etype, code, value = EVENT.unpack_from(buf)
            buf = buf[EVENT.size:]
            if etype == EV_ABS:
                if code == info.xcode:
                    x = value
                elif code == info.ycode:
                    y = value
                elif code == ABS_MT_TRACKING_ID:
                    contact = value >= 0
            elif etype == EV_KEY and code == BTN_TOUCH:
                contact = value == 1
            elif etype == EV_SYN and code == SYN_REPORT:
                if contact and x is not None and y is not None:
                    if not was:
                        yield ("down", x, y)
                    elif (x, y) != last:
                        yield ("move", x, y)
                    last = (x, y)
                elif was and not contact and last is not None:
                    yield ("up", last[0], last[1])
                was = contact and x is not None and y is not None
