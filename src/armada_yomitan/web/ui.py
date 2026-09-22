"""The web interface's state and commands."""

import http.server
import re
import secrets
import threading

from armada_yomitan import install_state, strings, syspackages
from armada_yomitan.anki.discovery import anki_installed_by_app, anki_ready
from armada_yomitan.capture import capture_png, png_size, probe_screens, screen_label
from armada_yomitan.console import log_error, looks_like_error
from armada_yomitan.ocr.engine import resolve_engine
from armada_yomitan.ocr.hit import crop_rect, hit_boxes
from armada_yomitan.ocr.image import mirror_jpeg
from armada_yomitan.ocr.rapid import warm_engine
from armada_yomitan.prefs import SCAN_DETAIL, clamp_anki_scale, load_prefs, save_prefs
from armada_yomitan.sessions import AreaSession, DrawSession, ScreenSession, TapSession
from armada_yomitan.web.anki_controls import AnkiControls
from armada_yomitan.web.http import make_handler
from armada_yomitan.web.sysdeps_controls import SysDepsControls
from armada_yomitan.yomitan.patch import kbd_patch_problems


class WebUI(AnkiControls, SysDepsControls):
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = secrets.token_urlsafe(16)
        self.clients, self.crops, self.crop_id = [], {}, 0
        self.done = threading.Event()
        self.after = None
        self.prefs = load_prefs(cfg.mode)
        cfg.capture_size = self.prefs["capture_size"]
        cfg.rapid_max_side = SCAN_DETAIL[self.prefs["scan_detail"]]
        self._nodes, self._probing, self._node_items, self._kbdlog = {}, False, [], 0
        self.draw, self.drawing = None, False
        self.anki_proc, self.anki_found = None, []
        self.sysdeps = self.new_sysdeps_state()
        self._anki_busy, self._anki_install, self._anki_cancelled = False, None, False
        self._anki_quitting, self._anki_watching = False, False
        self.last_status, self.last_state = strings.READY, self._state_msg(False, False, False)
        self._lock = threading.Lock()
        self.session = self._make_session()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    def _current_node(self):
        node = str(self.cfg.capture_node or "")
        if node and self.cfg.node_auto and node != self.prefs["capture_node"]:
            self.prefs["capture_node"] = node
            save_prefs(self.prefs)
        return node or self.prefs["capture_node"] or "0"

    def _prefs_msg(self):
        if self.cfg.capture_node and not self.cfg.node_auto:
            source = strings.SOURCE_NODE_FROM_OPTION.format(node=self.cfg.capture_node)
        else:
            source = self.prefs["capture_label"] or strings.SOURCE_AUTOMATIC
        return {"type": "prefs", **self.prefs, "source": source, "node": self._current_node(), "via_decky": syspackages.via_decky(),
                "anki_ready": anki_ready(self.prefs), "anki_running": self._anki_running(),
                "anki_own": anki_installed_by_app(self.prefs["anki_cmd"])}

    def _make_session(self):
        mode = self.prefs["mode"]
        if mode == "tap":
            return TapSession(self.cfg, self.on_status, self.on_hit, self.on_state)
        if mode == "manual":
            return AreaSession(self.cfg, self.on_status, self.on_hit, self.on_state,
                               get_areas=lambda: self.prefs["areas"])
        return ScreenSession(self.cfg, self.on_status, self.on_hit, self.on_state)

    def _state_msg(self, active, scanning, ready):
        return {"type": "state", "active": active, "scanning": scanning, "ready": ready, "mode": self.prefs["mode"]}

    def start(self):
        self._serving = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def shutdown(self):
        self.done.set()
        self._stop_anki()
        self.session.stop()
        if self.draw:
            self.draw.stop()
        if getattr(self, "_serving", False):             # shutdown() would wait forever on a server that never ran
            self.httpd.shutdown()
        self.httpd.server_close()

    def broadcast(self, msg):
        with self._lock:
            for q in list(self.clients):
                q.put(msg)

    def on_status(self, text, log=True):
        if log and looks_like_error(text):
            log_error(text)
        self.last_status = text
        self.broadcast({"type": "status", "text": text})

    def on_state(self, active, scanning, ready):
        self.last_state = self._state_msg(active, scanning, ready)
        self.broadcast(self.last_state)

    def _store(self, data, ctype):
        with self._lock:
            self.crop_id += 1
            cid = self.crop_id
            self.crops[cid] = (data, ctype)
            for old in [k for k in self.crops if k <= cid - 3]:
                del self.crops[old]
        return cid

    def on_hit(self, frame, px, py, hit, lines):
        if not hit:
            self.on_status(strings.NO_TEXT_NEAR_SPOT)
        msg = {"type": "hit" if hit else "nohit"}
        if hit:
            msg["query"] = hit.scan_text
        if self.prefs["show_preview"]:
            W, H = frame.get_width(), frame.get_height()
            x, y, cw, ch = crop_rect(px, py, W, H, self.cfg.preview_w, self.cfg.preview_h)
            ok, png = frame.new_subpixbuf(x, y, cw, ch).save_to_bufferv("png", [], [])
            if not ok:
                raise RuntimeError(strings.PREVIEW_NOT_ENCODED)
            cid = self._store(png, "image/png")
            msg.update(crop=cid, cw=cw, ch=ch, tap=[px - x, py - y])
            if hit:
                msg["box"], msg["span"] = hit_boxes(hit, x, y)
        self.broadcast(msg)

    def cmd_scan(self):
        if self.drawing:
            self.on_status(strings.FINISH_DRAWING_FIRST)
            return
        try:
            self.session.start()
        except Exception as e:
            self.on_status(strings.ERROR.format(error=e))

    def cmd_stop(self):
        self.session.stop()
        self.on_status(strings.BACK_TO_GAME)

    def cmd_quit(self):
        self.done.set()

    def cmd_reinstall(self):
        install_state.reset()
        self.after = "restart"
        self.done.set()

    def cmd_zoom(self, delta):
        self.prefs["yomi_zoom"] = round(min(2.0, max(0.7, self.prefs["yomi_zoom"] + delta)), 2)
        save_prefs(self.prefs)
        self.broadcast(self._prefs_msg())

    def cmd_pref(self, key, value):
        if key == "show_preview" and value in ("0", "1"):
            self.prefs["show_preview"] = value == "1"
        elif key == "anki_button" and value in ("0", "1"):
            self.prefs["anki_button"] = value == "1"
        elif key == "anki_scale":
            try:
                self.prefs["anki_scale"] = clamp_anki_scale(value)
            except ValueError:
                return
        elif key == "scan_detail" and value in SCAN_DETAIL:
            self.prefs["scan_detail"] = value
            self.cfg.rapid_max_side = SCAN_DETAIL[value]
            threading.Thread(target=self._preload, daemon=True).start()
        elif key == "mode" and value in ("screen", "tap", "manual"):
            if value != self.prefs["mode"]:
                if self.drawing:
                    self._finish_draw()
                self.session.stop()
                self.prefs["mode"] = value
                self.session = self._make_session()
                self.on_state(False, False, False)
                self.on_status(strings.READY)
        else:
            return
        save_prefs(self.prefs)
        self.broadcast(self._prefs_msg())

    def _on_mirror(self, frame):
        data, w, h = mirror_jpeg(frame)
        self.broadcast({"type": "mirror", "crop": self._store(data, "image/jpeg"), "cw": w, "ch": h})

    def _on_areas(self, areas, live):
        if live is None:
            self.prefs["areas"] = [list(a) for a in areas]
            save_prefs(self.prefs)
        self.broadcast({"type": "areas", "areas": areas, "live": live})

    def cmd_draw(self, on):
        if on == self.drawing:
            return
        if not on:
            self._finish_draw()
            return
        if self.prefs["mode"] != "manual":
            self.on_status(strings.CHOOSE_MANUAL_FIRST)
            return
        self.session.stop()                                    # only one thing may hold the touchscreen
        draw = DrawSession(self.cfg, self.on_status, self._on_mirror, self._on_areas, self.prefs["areas"])
        try:
            draw.start()
        except Exception as e:
            self.on_status(strings.ERROR.format(error=e))
            return
        self.draw, self.drawing = draw, True
        self.broadcast({"type": "draw", "on": True})

    def _finish_draw(self):
        areas = self.draw.stop() if self.draw else self.prefs["areas"]
        self.draw, self.drawing = None, False
        self.prefs["areas"] = areas
        save_prefs(self.prefs)
        self.broadcast({"type": "draw", "on": False})
        self.broadcast(self._prefs_msg())
        saved = strings.by_count(len(areas), strings.AREAS_SAVED_ONE, strings.AREAS_SAVED_MANY).format(count=len(areas))
        self.on_status(saved if areas else strings.NO_OCR_AREAS)

    def cmd_areas_clear(self):
        if self.draw:
            self.draw.clear()
        else:
            self.prefs["areas"] = []
            save_prefs(self.prefs)
            self.broadcast(self._prefs_msg())

    def cmd_draw_refresh(self):
        if self.draw:
            self.draw.refresh()

    def _preload(self):
        if resolve_engine(self.cfg) != "rapidocr":
            return
        self.on_status(strings.LOADING_OCR_MODEL)
        try:
            warm_engine(self.cfg)
            self.on_status(strings.READY)
        except Exception as e:
            self.on_status(strings.OCR_MODEL_FAILED.format(error=e))

    def cmd_nodes(self):
        with self._lock:
            if self._probing:
                return
            self._probing = True
        try:
            self.broadcast({"type": "nodes", "status": strings.NODES_LOOKING, "items": [], "node": self._current_node()})
            found, error = probe_screens(self.cfg)
            self._nodes = {n["id"]: n for n in found}
            items = self._node_items = []
            for n in found:
                w, h = n["size"]
                current = (str(self.cfg.capture_node) == n["id"] if self.cfg.capture_node
                           else self.cfg.capture_size == f"{w}x{h}")
                items.append({"id": n["id"], "label": screen_label(n["size"]), "size": strings.SCREEN_SIZE.format(width=w, height=h), "current": current})
            if items:
                status = strings.NODES_TAP_TO_CAPTURE
            else:
                status = (strings.NODES_NONE_FOUND_WHY.format(error=error[:90]) if error else strings.NODES_NONE_FOUND)
            self.broadcast({"type": "nodes", "status": status, "items": items, "node": self._current_node()})
        finally:
            with self._lock:
                self._probing = False

    def _nodes_note(self, text):
        self.broadcast({"type": "nodes", "status": text, "items": self._node_items, "node": self._current_node()})

    def cmd_node_manual(self, text):
        nid = (text or "").strip()
        if not re.fullmatch(r"\d{1,9}", nid):
            return self._nodes_note(strings.NODE_NOT_DIGITS)
        self._nodes_note(strings.NODE_TRYING.format(node=nid))
        try:
            size = png_size(capture_png(self.cfg, node=nid, timeout=6))
        except RuntimeError as e:
            log_error(f"Node {nid} didn't deliver a frame: {e}")
            return self._nodes_note(strings.NODE_NO_FRAME.format(node=nid, reason=str(e)[:100]))
        if not size:
            return self._nodes_note(strings.NODE_NOT_A_PICTURE.format(node=nid))
        with self._lock:
            self._nodes[nid] = {"id": nid, "name": "typed by hand", "size": size}
        self.cmd_node(nid)
        self.broadcast({"type": "nodes", "close": True})

    def cmd_kbdlog(self, text):
        self._kbdlog += 1
        if self._kbdlog > 10:
            return
        problems = kbd_patch_problems()
        log_error("Keyboard: " + (text or "")[:300],
                  ["Problems with the patch of Yomitan's folder: " + "; ".join(problems)] if problems else
                  ["Yomitan's folder looks patched, so the script probably didn't run or hit an error in the page.",
                   "Open Yomitan's settings alone with: armada-yomitan --yomitan-settings"])
        self.on_status(strings.KEYBOARD_DID_NOT_START, log=False)

    def cmd_node(self, nid):
        node = self._nodes.get(nid)
        if not node:
            return
        w, h = node["size"]
        label = screen_label(node["size"])
        self.cfg.capture_node, self.cfg.node_auto = nid, True
        self.cfg.capture_size = self.prefs["capture_size"] = f"{w}x{h}"
        self.prefs["capture_label"] = strings.SCREEN_WITH_SIZE.format(label=label, width=w, height=h)
        save_prefs(self.prefs)
        self.broadcast(self._prefs_msg())
        self.on_status(strings.CAPTURING_SCREEN.format(label=label.lower(), width=w, height=h))

    def _handler(self):
        return make_handler(self)
