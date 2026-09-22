"""System-packages commands of the web interface."""

import sys

from armada_yomitan import strings, syspackages
from armada_yomitan.console import log_error


class SysDepsControls:
    def new_sysdeps_state(self):
        return {"checked": False, "busy": False, "missing": [], "packages": [], "needs_reboot": False,
                "done": False, "staged": False, "status": strings.SYSDEPS_CHECKING, "show": False}

    def _sysdeps_msg(self, **more):
        return {"type": "sysdeps", **self.sysdeps, **more}

    def _sysdeps_update(self, **fields):
        self.sysdeps.update(fields)
        self.broadcast(self._sysdeps_msg())

    def cmd_sysdeps_check(self, show=False):
        with self._lock:
            if self.sysdeps["busy"]:
                return
        missing = syspackages.missing()
        required, optional = syspackages.plan(syspackages.run_checks())
        needed = bool(required)
        if self.sysdeps["staged"] and missing:                       # installed earlier in this run: still "missing" until the reboot
            self._sysdeps_update(checked=True, missing=[{"label": l, "packages": p, "optional": o} for l, p, o in missing],
                                 packages=[], done=True, needs_reboot=True, show=show,
                                 status=strings.SYSDEPS_WAITING_FOR_RESTART)
            return
        root = syspackages.can_install_here()
        if not missing:
            status = strings.SYSDEPS_ALL_PRESENT
        elif not root:
            status = strings.NEEDS_ROOT
        elif needed:
            status = strings.SYSDEPS_SOME_MISSING
        else:
            status = strings.SYSDEPS_ONLY_OPTIONAL_MISSING
        self._sysdeps_update(checked=True, missing=[{"label": l, "packages": p, "optional": o} for l, p, o in missing],
                             packages=required + optional if root else [], done=not missing,
                             needs_reboot=False, status=status, show=needed or show)

    def cmd_sysdeps_install(self):
        if not syspackages.can_install_here():
            return
        with self._lock:
            if self.sysdeps["busy"]:
                return
            self.sysdeps["busy"] = True
        self._sysdeps_update(busy=True, done=False, status=strings.SYSDEPS_INSTALLING)

        def line(text):
            print(text, file=sys.stderr, flush=True)
            self.broadcast({"type": "sysdeps", "line": text})

        try:
            result = syspackages.install(on_line=line)
            if result == "nothing":
                self._sysdeps_update(busy=False, done=True, missing=[], status=strings.SYSDEPS_ALREADY_INSTALLED)
            else:
                self._sysdeps_update(busy=False, done=True, needs_reboot=True, staged=True,
                                     status=strings.SYSDEPS_INSTALLED_RESTART)
        except Exception as e:
            log_error(f"System packages: {e}")
            self._sysdeps_update(busy=False, status=str(e)[:300])

    def cmd_sysdeps_reboot(self):
        try:
            syspackages.reboot()
        except RuntimeError as e:
            log_error(f"System packages: {e}")
            self._sysdeps_update(status=str(e))
