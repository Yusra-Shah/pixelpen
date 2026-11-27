"""Phase 5b: interpreter for the quadruples, plus SVG export.

Pen model
  * the pen starts at (0, 0), facing up, pen down, colour black
  * y grows upwards (mathematical axes); turn is counterclockwise, in degrees
  * forward draws a line only while the pen is down; moveto never draws
  * circle and square are centred on the given point; line P, Q is drawn
    between the two points.  Shapes and lines are explicit drawing commands,
    so they are drawn even while the pen is up; penup only stops the trail
    left by forward.
  * the pen position and heading are not changed by circle, square or line

Arithmetic: '/' truncates toward zero and '%' keeps the sign of the left
operand (like C).

Runtime errors: division by zero, negative size, a variable read before it was
given a value, and exceeding the step limit (default 200000 instructions).
"""

import math
from collections import namedtuple

from .diagnostics import Diagnostic

STEP_LIMIT = 200000
LOG_LIMIT = 1000

# kind is 'line', 'circle' or 'square'; data is
#   line:   (x1, y1, x2, y2)       circle: (cx, cy, radius)
#   square: (cx, cy, side)
Draw = namedtuple("Draw", "kind color data")


class PixelPenRuntimeError(Exception):
    def __init__(self, message, line):
        Exception.__init__(self, message)
        self.message = message
        self.line = line


class RuntimeResult:
    def __init__(self):
        self.draws = []
        self.log = []
        self.error = None            # Diagnostic or None
        self.steps = 0
        self.variables = {}          # final value of every user variable
        self.pen = {"x": 0.0, "y": 0.0, "heading": 90.0,
                    "down": True, "color": "#000000"}

    @property
    def ok(self):
        return self.error is None


def trunc_div(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def show(value):
    if isinstance(value, tuple):
        return "(%d, %d)" % value
    return str(value)


class Interpreter:
    def __init__(self, quads, temps=(), step_limit=STEP_LIMIT):
        self.quads = quads
        self.temps = set(temps)
        self.step_limit = step_limit
        self.result = RuntimeResult()
        self.env = {}
        self.params = []
        self.targets = {q.label: i for i, q in enumerate(quads) if q.label}

    # -- helpers ---------------------------------------------------------------

    def log(self, text):
        log = self.result.log
        if len(log) < LOG_LIMIT:
            log.append(text)
        elif len(log) == LOG_LIMIT:
            log.append("... log truncated after %d lines" % LOG_LIMIT)

    def value(self, text, line):
        if text[0].isdigit():
            return int(text)
        if text[0] == "#":
            return text.upper()
        if text not in self.env:
            raise PixelPenRuntimeError(
                "variable '%s' has no value yet" % text, line)
        return self.env[text]

    # -- execution -------------------------------------------------------------

    def run(self):
        quads = self.quads
        pc = 0
        res = self.result
        try:
            while True:
                res.steps += 1
                if res.steps > self.step_limit:
                    raise PixelPenRuntimeError(
                        "step limit of %d instructions exceeded "
                        "(possible infinite loop)" % self.step_limit,
                        quads[pc].line)
                q = quads[pc]
                op = q.op
                pc += 1
                if op == "halt":
                    break
                if op == "goto":
                    pc = self.targets[q.result]
                elif op.startswith("if"):
                    a = self.value(q.arg1, q.line)
                    b = self.value(q.arg2, q.line)
                    if self.compare(op[2:], a, b):
                        pc = self.targets[q.result]
                elif op == "=":
                    self.env[q.result] = self.value(q.arg1, q.line)
                elif op == "mkpoint":
                    self.env[q.result] = (self.value(q.arg1, q.line),
                                          self.value(q.arg2, q.line))
                elif op == "minus":
                    self.env[q.result] = -self.value(q.arg1, q.line)
                elif op == "param":
                    self.params.append(self.value(q.arg1, q.line))
                elif op == "call":
                    n = int(q.arg2)
                    args = self.params[len(self.params) - n:]
                    del self.params[len(self.params) - n:]
                    self.call(q.arg1, args, q.line)
                else:
                    self.env[q.result] = self.arith(
                        op, self.value(q.arg1, q.line),
                        self.value(q.arg2, q.line), q.line)
        except PixelPenRuntimeError as err:
            res.error = Diagnostic("runtime", err.line, 1, err.message)
            self.log("runtime error (line %d): %s" % (err.line, err.message))
        res.variables = {k: v for k, v in self.env.items()
                         if k not in self.temps}
        return res

    @staticmethod
    def compare(rel, a, b):
        if rel == "<":
            return a < b
        if rel == ">":
            return a > b
        if rel == "<=":
            return a <= b
        if rel == ">=":
            return a >= b
        if rel == "==":
            return a == b
        return a != b

    @staticmethod
    def arith(op, a, b, line):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if b == 0:
            raise PixelPenRuntimeError("division by zero", line)
        q = trunc_div(a, b)
        return q if op == "/" else a - b * q

    # -- the drawing commands --------------------------------------------------

    def call(self, name, args, line):
        pen = self.result.pen
        draws = self.result.draws
        if name == "forward":
            n = args[0]
            rad = math.radians(pen["heading"])
            nx = pen["x"] + n * math.cos(rad)
            ny = pen["y"] + n * math.sin(rad)
            if pen["down"]:
                draws.append(Draw("line", pen["color"],
                                  (pen["x"], pen["y"], nx, ny)))
            self.log("forward %d: (%.2f, %.2f) -> (%.2f, %.2f)%s" % (
                n, pen["x"], pen["y"], nx, ny,
                "" if pen["down"] else "  [pen up, no line]"))
            pen["x"], pen["y"] = nx, ny
        elif name == "turn":
            pen["heading"] = (pen["heading"] + args[0]) % 360
            self.log("turn %d: heading is now %.1f degrees" % (
                args[0], pen["heading"]))
        elif name == "moveto":
            pen["x"], pen["y"] = float(args[0][0]), float(args[0][1])
            self.log("moveto %s" % show(args[0]))
        elif name == "penup":
            pen["down"] = False
            self.log("penup")
        elif name == "pendown":
            pen["down"] = True
            self.log("pendown")
        elif name == "pencolor":
            pen["color"] = args[0]
            self.log("pencolor %s" % args[0])
        elif name in ("circle", "square"):
            (cx, cy), size = args
            if size < 0:
                raise PixelPenRuntimeError(
                    "negative size: %s %s" % (
                        "radius" if name == "circle" else "side length", size),
                    line)
            draws.append(Draw(name, pen["color"], (cx, cy, size)))
            self.log("%s at %s, %s %d" % (
                name, show((cx, cy)),
                "radius" if name == "circle" else "side", size))
        elif name == "line":
            (x1, y1), (x2, y2) = args
            draws.append(Draw("line", pen["color"], (x1, y1, x2, y2)))
            self.log("line %s to %s" % (show(args[0]), show(args[1])))


def run(quads, temps=(), step_limit=STEP_LIMIT):
    """Execute quadruples and return a RuntimeResult."""
    return Interpreter(quads, temps, step_limit).run()


# ---------------------------------------------------------------------------
# SVG export
# ---------------------------------------------------------------------------

def bounding_box(draws):
    """(min_x, min_y, max_x, max_y) of the drawing, always including (0, 0)."""
    xs, ys = [0.0], [0.0]
    for d in draws:
        if d.kind == "line":
            x1, y1, x2, y2 = d.data
            xs += [x1, x2]
            ys += [y1, y2]
        else:
            cx, cy, s = d.data
            r = s if d.kind == "circle" else s / 2.0
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
    return min(xs), min(ys), max(xs), max(ys)


def to_svg(draws, size=600):
    """Return the drawing as an SVG document (y axis flipped to point up)."""
    min_x, min_y, max_x, max_y = bounding_box(draws)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    margin = span * 0.08 + 5
    width = (max_x - min_x) + 2 * margin
    height = (max_y - min_y) + 2 * margin
    stroke = max(span / 250.0, 0.5)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="%.3f %.3f %.3f %.3f">' % (
               size, max(int(size * height / width), 1),
               min_x - margin, -(max_y + margin), width, height),
           '<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" fill="white"/>'
           % (min_x - margin, -(max_y + margin), width, height)]
    for d in draws:
        common = 'stroke="%s" stroke-width="%.3f" fill="none"' % (
            d.color, stroke)
        if d.kind == "line":
            x1, y1, x2, y2 = d.data
            out.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" %s/>'
                       % (x1, -y1, x2, -y2, common))
        elif d.kind == "circle":
            cx, cy, r = d.data
            out.append('<circle cx="%.3f" cy="%.3f" r="%.3f" %s/>'
                       % (cx, -cy, r, common))
        else:
            cx, cy, s = d.data
            out.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" %s/>'
                       % (cx - s / 2.0, -(cy + s / 2.0), s, s, common))
    out.append("</svg>")
    return "\n".join(out)
