#!/usr/bin/env python3
"""Claude Code status line styled after the LazyVim / tokyonight-moon lualine bar.

 MODE  branch  root . session                        tokens  model  ctx%

Glyphs are built from code points at runtime so this file stays pure ASCII.
"""
import fcntl
import json
import os
import struct
import sys
import termios

# tokyonight-moon
C = {
    "black": "1b1d2b",
    "blue": "82aaff",
    "blue1": "65bcff",
    "green": "c3e88d",
    "green1": "4fd6be",
    "yellow": "ffc777",
    "orange": "ff966c",
    "red": "ff757f",
    "magenta": "c099ff",
    "fg": "c8d3f5",
    "fg_sidebar": "828bb8",
    "fg_gutter": "3b4261",
    "bg_statusline": "1e2030",
}

# lualine/themes/_tokyonight.lua: section a bg per mode, section b fg matches it
MODE_BG = {
    "NORMAL": C["blue"],
    "INSERT": C["green"],
    "VISUAL": C["magenta"],
    "V-LINE": C["magenta"],
    "V-BLOCK": C["magenta"],
    "REPLACE": C["red"],
    "COMMAND": C["yellow"],
    "TERMINAL": C["green1"],
}

# Claude does not put permission_mode in the status line payload, so hooks
# mirror it to ~/.claude/session-mode/<session_id>. Until a hook has fired in
# a session there is no file, so fall back to the configured default mode.
CLAUDE_DIR = os.path.expanduser("~/.claude")
MODE_DIR = os.path.join(CLAUDE_DIR, "session-mode")
PERM_MODES = {
    "plan": ("PLAN", "magenta"),
    "acceptEdits": ("ACCEPT EDITS", "green"),
    "bypassPermissions": ("BYPASS", "red"),
    "dontAsk": ("DONT ASK", "yellow"),
    "auto": ("AUTO", "blue1"),
    "default": ("DEFAULT", "fg_sidebar"),
}

SEP_R = chr(0xE0B0)
SEP_L = chr(0xE0B2)
SEP_THIN = chr(0xE0B1)
ICON_BRANCH = chr(0xE0A0)
ICON_ROOT = chr(0xF126D)
ICON_SESSION = chr(0xF075)
ICON_MODEL = chr(0xF0E7)
ELLIPSIS = chr(0x2026)
RESET = "\x1b[0m"

# Claude wraps the status line in a box with paddingLeft 2 / paddingRight 1-2.
MARGIN = 5


def fg(h):
    return "\x1b[38;2;%d;%d;%dm" % tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def bg(h):
    return "\x1b[48;2;%d;%d;%dm" % tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _ioctl_cols(fd):
    return struct.unpack("hh", fcntl.ioctl(fd, termios.TIOCGWINSZ, "    "))[1]


def term_width():
    """Claude gives the command piped stdio, so try the controlling tty first."""
    try:
        with open("/dev/tty") as tty:
            cols = _ioctl_cols(tty)
            if cols:
                return cols, "tty"
    except Exception:
        pass
    for fd in (1, 2, 0):
        try:
            cols = _ioctl_cols(fd)
            if cols:
                return cols, f"fd{fd}"
        except Exception:
            pass
    try:
        cols = int(os.environ.get("COLUMNS", 0))
        if cols:
            return cols, "env"
    except ValueError:
        pass
    return 0, "none"


def human(n):
    for div, suffix in ((1_000_000, "M"), (1_000, "k")):
        if n >= div:
            return f"{n / div:.1f}".removesuffix(".0") + suffix
    return str(n)


def short(name, limit):
    name = name.strip().splitlines()[0].strip() if name.strip() else ""
    return name[: limit - 1] + ELLIPSIS if len(name) > limit else name


def configured_default_mode():
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(CLAUDE_DIR, name)) as fh:
                mode = (json.load(fh).get("permissions") or {}).get("defaultMode")
            if mode:
                return mode
        except (OSError, ValueError):
            pass
    return "default"


def permission_mode(session_id):
    mode = ""
    try:
        with open(os.path.join(MODE_DIR, session_id)) as fh:
            mode = fh.read().strip()
    except OSError:
        pass
    return PERM_MODES.get(mode or configured_default_mode())


def fit_branch(b, limit):
    """Branches are <owner>/<topic>; the topic is the informative half."""
    if len(b) <= limit:
        return b
    tail = b.rsplit("/", 1)[-1]
    return tail if len(tail) <= limit else ELLIPSIS + tail[-(limit - 1) :]


def git_branch(start):
    """Read .git/HEAD directly - no subprocess, this runs on every refresh."""
    d = os.path.abspath(start or ".")
    while True:
        g = os.path.join(d, ".git")
        head = None
        if os.path.isdir(g):
            head = os.path.join(g, "HEAD")
        elif os.path.isfile(g):
            try:
                with open(g) as fh:
                    line = fh.read().strip()
            except OSError:
                return ""
            if line.startswith("gitdir:"):
                p = line.split(":", 1)[1].strip()
                head = os.path.join(p if os.path.isabs(p) else os.path.join(d, p), "HEAD")
        if head:
            try:
                with open(head) as fh:
                    ref = fh.read().strip()
            except OSError:
                return ""
            prefix = "ref: refs/heads/"
            return ref[len(prefix) :] if ref.startswith(prefix) else ref[:7]
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


class Bar:
    """Powerline blocks. Each block is a list of (text, fg) sharing one bg."""

    def __init__(self):
        self.blocks = []

    def add(self, parts, block_bg, bold=False, key=None):
        parts = [(t, f) for t, f in parts if t]
        if parts:
            self.blocks.append((parts, block_bg, bold, key))

    def drop(self, key):
        before = len(self.blocks)
        self.blocks = [b for b in self.blocks if b[3] != key]
        return len(self.blocks) != before

    @staticmethod
    def _inner(parts):
        return sum(len(t) for t, _ in parts) + 3 * (len(parts) - 1)

    def width(self):
        return sum(self._inner(p) + 2 for p, _, _, _ in self.blocks) + len(self.blocks)

    def _body(self, parts, block_bg, bold):
        out = bg(block_bg) + ("\x1b[1m" if bold else "")
        for i, (text, f) in enumerate(parts):
            if i:
                out += fg(C["fg_gutter"]) + f" {SEP_THIN} "
            out += fg(f) + text
        return f"{bg(block_bg)} {out} \x1b[22m"

    def render(self, side, outer):
        out = ""
        for i, (parts, block_bg, bold, _key) in enumerate(self.blocks):
            if side == "left":
                out += self._body(parts, block_bg, bold)
                nxt = self.blocks[i + 1][1] if i + 1 < len(self.blocks) else outer
                out += bg(nxt) + fg(block_bg) + SEP_R
            else:
                prev = self.blocks[i - 1][1] if i else outer
                out += bg(prev) + fg(block_bg) + SEP_L
                out += self._body(parts, block_bg, bold)
        return out


def main():
    try:
        d = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(d, dict):
        return

    ws = d.get("workspace") or {}
    wt = d.get("worktree") or {}
    cwd = ws.get("current_dir") or d.get("cwd") or ""

    mode = ((d.get("vim") or {}).get("mode") or "").upper()
    accent = MODE_BG.get(mode, C["blue"])
    branch = wt.get("branch") or git_branch(cwd)
    root = os.path.basename(wt.get("path") or ws.get("project_dir") or cwd)

    name = d.get("session_name") or ""
    if not name.strip():
        sid = (d.get("session_id") or "")[:6]
        name = f"{os.path.basename(cwd) or 'session'}:{sid}" if sid else os.path.basename(cwd)

    cw = d.get("context_window") or {}
    used = cw.get("total_input_tokens")
    pct = cw.get("used_percentage")
    model = (d.get("model") or {}).get("display_name") or ""

    right = Bar()
    perm = permission_mode(d.get("session_id") or "")
    if perm:
        label, colour = perm
        right.add([(label, C["black"])], C[colour], bold=True, key="perm")
    if used is not None:
        right.add([(human(used), C["fg_sidebar"])], C["bg_statusline"], key="tokens")
    if model:
        right.add([(f"{ICON_MODEL} {model}", accent)], C["fg_gutter"], key="model")
    if pct is not None:
        level = (
            C["red"] if pct >= 90 else C["orange"] if pct >= 75 else C["yellow"] if pct >= 50 else C["green"]
        )
        right.add([(f"{pct:.0f}%", C["black"])], level, bold=True, key="pct")

    def build_left(name_lim, root_lim, branch_lim, with_root=True):
        left = Bar()
        left.add([(mode or "CLAUDE", C["black"])], accent, bold=True)
        if branch and branch_lim:
            left.add([(f"{ICON_BRANCH} {fit_branch(branch, branch_lim)}", accent)], C["fg_gutter"])
        parts = []
        if root and with_root:
            parts.append((f"{ICON_ROOT} {short(root, root_lim)}", C["blue1"]))
        if name:
            parts.append((f"{ICON_SESSION} {short(name, name_lim)}", C["fg"]))
        left.add(parts, C["bg_statusline"])
        return left

    # Progressively give up detail until the bar fits: shrink text, then drop
    # the raw token count, the model, the root dir, and finally the branch.
    PLANS = (
        (60, 28, 40, True),
        (44, 24, 34, True),
        (30, 18, 26, True),
        (20, 14, 18, True),
        (14, 10, 12, True),
        (14, 0, 12, False),
        (12, 0, 0, False),
        (8, 0, 0, False),
    )

    cols, _method = term_width()
    budget = cols - MARGIN if cols else 0

    left = build_left(*PLANS[0])
    if budget:
        for plan in PLANS:
            left = build_left(*plan)
            if left.width() + right.width() <= budget:
                break
        for key in ("tokens", "model", "perm", "pct"):
            if left.width() + right.width() <= budget:
                break
            right.drop(key)

    pad = max(0, budget - left.width() - right.width()) if budget else 1
    print(
        RESET
        + left.render("left", C["bg_statusline"])
        + bg(C["bg_statusline"])
        + " " * pad
        + right.render("right", C["bg_statusline"])
        + RESET
    )


main()
