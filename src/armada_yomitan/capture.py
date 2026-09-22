"""Top-screen capture."""

import json
import os
import re
import shlex
import struct
import subprocess
import threading

from armada_yomitan import strings
from armada_yomitan.console import log_error


def _run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _nodes_from_pw_dump(out):
    nodes = []
    for obj in json.loads(out or "[]"):
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = obj.get("info", {}).get("props", {})
        label = " ".join(str(props.get(k, "")) for k in ("node.name", "node.description", "media.name"))
        if "gamescope" in label.lower():
            nodes.append((obj["id"], props.get("node.name", "?")))
    return nodes


def _nodes_from_pw_cli(out):
    blocks = []
    for line in out.splitlines():
        m = re.match(r"\s*id (\d+), type PipeWire:Interface:Node", line)
        if m:
            blocks.append([int(m.group(1)), "?", False])
        elif blocks:
            if "gamescope" in line.lower():
                blocks[-1][2] = True
            n = re.search(r'node\.name = "(.*)"', line)
            if n:
                blocks[-1][1] = n.group(1)
    return [(i, name) for i, name, hit in blocks if hit]


def _nodes_from_wpctl(out):
    found = []
    for line in out.splitlines():
        m = re.search(r"(\d+)\.\s+(.*gamescope.*)", line, re.I)
        if m:
            found.append((int(m.group(1)), m.group(2).strip()))
    return found


def _nodes_from_journal(out):
    ids = []
    for i in re.findall(r"stream available on node ID: (\d+)", out):
        if int(i) in ids:
            ids.remove(int(i))
        ids.append(int(i))
    return [(i, "from the log, may be stale") for i in ids[-4:]]


def list_capture_nodes():
    attempts = (
        (["pw-dump"], _nodes_from_pw_dump),
        (["pw-cli", "ls", "Node"], _nodes_from_pw_cli),
        (["wpctl", "status"], _nodes_from_wpctl),
        (["journalctl", "-b", "--no-pager", "-g", "stream available on node ID"], _nodes_from_journal),
    )
    for cmd, parse in attempts:
        out = _run(cmd)
        if out:
            try:
                nodes = parse(out)
            except ValueError:
                continue
            if nodes:
                return nodes
    return []


def resolve_node(cfg):
    if cfg.capture_node:
        return cfg.capture_node
    if cfg.capture_size:
        found = find_node_by_size(cfg, cfg.capture_size)
        if found:
            cfg.capture_node, cfg.node_auto = found, True
            return found
        raise RuntimeError(strings.CAPTURE_SCREEN_NOT_FOUND.format(size=cfg.capture_size))
    nodes = list_capture_nodes()
    if len(nodes) == 1:
        return str(nodes[0][0])
    if not nodes:
        raise RuntimeError(strings.CAPTURE_NO_NODE)
    raise RuntimeError(strings.CAPTURE_MANY_NODES.format(count=len(nodes), nodes=nodes))


def _capture_once(cfg, node, timeout):
    try:
        cmd = cfg.capture_cmd.format(node=node)
    except KeyError as e:
        raise RuntimeError(strings.CAPTURE_BAD_COMMAND.format(reason=e))
    try:
        r = subprocess.run(shlex.split(cmd), capture_output=True, timeout=timeout)
    except FileNotFoundError as e:
        raise RuntimeError(strings.CAPTURE_TOOL_MISSING.format(tool=e.filename))
    except subprocess.TimeoutExpired:
        raise RuntimeError(strings.CAPTURE_TIMED_OUT)
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace")
        if 'no element "pipewiresrc"' in err:
            raise RuntimeError(strings.CAPTURE_NO_PIPEWIRE_PLUGIN)
        raise RuntimeError(strings.CAPTURE_FAILED.format(output=err[-300:]))
    if not r.stdout.startswith(b"\x89PNG"):
        raise RuntimeError(strings.CAPTURE_NOT_A_PNG)
    return r.stdout


def capture_png(cfg, node=None, timeout=8):
    if cfg.image:
        with open(cfg.image, "rb") as f:
            return f.read()
    if node:
        return _capture_once(cfg, node, timeout)
    try:
        return _capture_once(cfg, resolve_node(cfg), timeout)
    except RuntimeError:
        if not (cfg.node_auto and cfg.capture_size):
            raise
        cfg.capture_node, cfg.node_auto = "", False     # the cached id went stale (the game restarted): look again
        return _capture_once(cfg, resolve_node(cfg), timeout)


TOP_SIZES = {(1920, 1080), (1080, 1920)}


BOTTOM_SIZES = {(1240, 1080), (1080, 1240)}


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return None
    return struct.unpack(">II", data[16:24])


def screen_label(size):
    return (strings.SCREEN_TOP if tuple(size) in TOP_SIZES else strings.SCREEN_BOTTOM if tuple(size) in BOTTOM_SIZES
            else strings.SCREEN_OTHER)


def _screen_rank(size):
    return 0 if tuple(size) in TOP_SIZES else 2 if tuple(size) in BOTTOM_SIZES else 1


def ancestor_pids():
    pids, pid = set(), os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


def probe_screens(cfg, timeout=6):
    ancestors, found, errors = ancestor_pids(), [], []
    lock = threading.Lock()

    def work(nid, name):
        try:
            size = png_size(capture_png(cfg, node=str(nid), timeout=timeout))
        except RuntimeError as e:
            size = None
            with lock:
                errors.append(str(e))
        if size:
            with lock:
                found.append({"id": str(nid), "name": name, "size": size})

    threads = []
    for nid, name in list_capture_nodes():
        owner = re.search(r"pid:(\d+)", name)
        if owner and int(owner.group(1)) in ancestors:
            continue
        threads.append(threading.Thread(target=work, args=(nid, name), daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    found.sort(key=lambda n: (_screen_rank(n["size"]), int(n["id"]) if n["id"].isdigit() else 0))
    if not found and errors:
        log_error("Couldn't grab a frame from any screen", sorted(set(errors)))
    return found, ("" if found or not errors else errors[0])


def find_node_by_size(cfg, size):
    for n in probe_screens(cfg)[0]:
        if f"{n['size'][0]}x{n['size'][1]}" == size:
            return n["id"]
    return None
