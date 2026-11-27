"""Phase 4b: semantic analysis (symbol table and type checking).

There is one global scope.  Types are 'int', 'color', 'point' and 'bool'; bool
only appears as the result of a comparison.  The pseudo type 'err' marks a name
that was not declared: it is entered into the table the first time it is used
so that the error is reported once, and 'err' silences follow-up errors.

Rules checked
  * arithmetic (+ - * / % and unary -) needs int operands
  * < > <= >= need two ints; == != need two ints or two colors
  * and / or / not need bool operands; if / while conditions must be bool
  * forward, turn and repeat take int; moveto takes point; pencolor takes color
  * circle and square take (point, int); line takes (point, point)
  * a declaration needs an initializer of the declared type; no redeclaration
  * assignment must keep the variable's type
  * division or modulo by a constant 0 is an error; 'repeat 0' is a warning
"""

from collections import OrderedDict

from . import astbuild as A
from .diagnostics import Diagnostic

INT, COLOR, POINT, BOOL, ERR = "int", "color", "point", "bool", "err"
ARITH = ("+", "-", "*", "/", "%")
ORDER = ("<", ">", "<=", ">=")
EQUALITY = ("==", "!=")


class Symbol:
    """A symbol table entry."""

    def __init__(self, name, type_, line, col):
        self.name = name
        self.type = type_
        self.line = line
        self.col = col
        self.uses = 0

    def __repr__(self):
        return "Symbol(%s:%s)" % (self.name, self.type)


class SemanticResult:
    def __init__(self, symbols, diagnostics):
        self.symbols = symbols              # OrderedDict name -> Symbol
        self.diagnostics = diagnostics

    @property
    def errors(self):
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self):
        return [d for d in self.diagnostics if d.severity == "warning"]


def const_int(expr):
    """Value of a constant int expression, or None if it is not constant."""
    if isinstance(expr, A.Num):
        return expr.value
    if isinstance(expr, A.Unary) and expr.op == "-":
        v = const_int(expr.operand)
        return None if v is None else -v
    if isinstance(expr, A.Binary) and expr.op in ARITH:
        a, b = const_int(expr.left), const_int(expr.right)
        if a is None or b is None:
            return None
        if expr.op == "+":
            return a + b
        if expr.op == "-":
            return a - b
        if expr.op == "*":
            return a * b
        if b == 0:
            return None
        q = abs(a) // abs(b)
        q = q if (a >= 0) == (b >= 0) else -q
        return q if expr.op == "/" else a - b * q
    return None


class Analyzer:
    def __init__(self):
        self.symbols = OrderedDict()
        self.diagnostics = []

    def _error(self, node, message):
        self.diagnostics.append(
            Diagnostic("semantic", node.line, node.col, message))

    def _warning(self, node, message):
        self.diagnostics.append(
            Diagnostic("semantic", node.line, node.col, message, "warning"))

    # -- entry point ---------------------------------------------------------------

    def analyze(self, program):
        for stmt in program.stmts:
            self._stmt(stmt)
        return SemanticResult(self.symbols, self.diagnostics)

    # -- statements --------------------------------------------------------------------

    def _stmt(self, s):
        if s is None:
            return
        getattr(self, "_s_" + type(s).__name__)(s)

    def _s_Block(self, s):
        for stmt in s.stmts:
            self._stmt(stmt)

    def _s_Decl(self, s):
        init_type = self._expr(s.init)
        existing = self.symbols.get(s.name)
        if existing is not None and existing.type != ERR:
            self._error(s, "'%s' is already declared (first declared on "
                           "line %d)" % (s.name, existing.line))
            return
        if init_type not in (s.type_name, ERR):
            self._error(s, "cannot initialize %s variable '%s' with a value "
                           "of type %s" % (s.type_name, s.name, init_type))
        self.symbols[s.name] = Symbol(s.name, s.type_name, s.line, s.col)

    def _s_Assign(self, s):
        sym = self._lookup(s.name, s)
        value_type = self._expr(s.value)
        if sym.type != ERR and value_type not in (sym.type, ERR):
            self._error(s, "cannot assign %s to '%s' of type %s"
                        % (value_type, s.name, sym.type))

    def _expect(self, expr, wanted, what):
        """Check expr has type wanted; what names the argument for messages."""
        got = self._expr(expr)
        if got not in (wanted, ERR):
            self._error(expr, "%s must be %s, found %s" % (what, wanted, got))

    def _s_Command(self, s):
        if s.arg is None:
            return
        wanted = {"forward": INT, "turn": INT, "moveto": POINT,
                  "pencolor": COLOR}[s.name]
        self._expect(s.arg, wanted, "the argument of '%s'" % s.name)

    def _s_Shape(self, s):
        if s.kind in ("circle", "square"):
            second = "radius" if s.kind == "circle" else "side length"
            self._expect(s.first, POINT, "the center of '%s'" % s.kind)
            self._expect(s.second, INT, "the %s of '%s'" % (second, s.kind))
        else:
            self._expect(s.first, POINT, "the start of 'line'")
            self._expect(s.second, POINT, "the end of 'line'")

    def _s_Repeat(self, s):
        self._expect(s.count, INT, "the count of 'repeat'")
        if const_int(s.count) == 0:
            self._warning(s, "'repeat 0': the loop body never runs")
        self._stmt(s.body)

    def _condition(self, s, keyword):
        got = self._expr(s.cond)
        if got not in (BOOL, ERR):
            self._error(s.cond, "the condition of '%s' must be a comparison "
                                "(bool), found %s" % (keyword, got))

    def _s_While(self, s):
        self._condition(s, "while")
        self._stmt(s.body)

    def _s_If(self, s):
        self._condition(s, "if")
        self._stmt(s.then)
        if s.otherwise is not None:
            self._stmt(s.otherwise)

    # -- expressions ----------------------------------------------------------------------

    def _lookup(self, name, node):
        sym = self.symbols.get(name)
        if sym is None:
            self._error(node, "'%s' is not declared" % name)
            sym = Symbol(name, ERR, node.line, node.col)
            self.symbols[name] = sym
        sym.uses += 1
        return sym

    def _expr(self, e):
        return getattr(self, "_e_" + type(e).__name__)(e)

    def _e_Num(self, e):
        return INT

    def _e_Hex(self, e):
        return COLOR

    def _e_Var(self, e):
        return self._lookup(e.name, e).type

    def _e_Point(self, e):
        for coord in (e.x, e.y):
            t = self._expr(coord)
            if t not in (INT, ERR):
                self._error(coord, "point coordinates must be int, found %s" % t)
        return POINT

    def _e_Unary(self, e):
        t = self._expr(e.operand)
        if e.op == "not":
            if t not in (BOOL, ERR):
                self._error(e, "operator 'not' needs a bool operand, found %s" % t)
            return BOOL
        if t == ERR:
            return ERR
        if t != INT:
            self._error(e, "unary '-' needs an int operand, found %s" % t)
        return INT

    def _e_Binary(self, e):
        lt, rt = self._expr(e.left), self._expr(e.right)
        op = e.op
        if op in ARITH:
            if op in ("/", "%") and const_int(e.right) == 0:
                word = "division" if op == "/" else "modulo"
                self._error(e, "%s by constant 0" % word)
            if ERR in (lt, rt):
                return ERR
            if lt != INT or rt != INT:
                self._error(e, "operator '%s' needs int operands, found %s "
                               "and %s" % (op, lt, rt))
            return INT
        if op in ORDER:
            if ERR not in (lt, rt) and (lt != INT or rt != INT):
                self._error(e, "operator '%s' needs int operands, found %s "
                               "and %s" % (op, lt, rt))
            return BOOL
        if op in EQUALITY:
            if ERR not in (lt, rt) and not (lt == rt and lt in (INT, COLOR)):
                self._error(e, "operator '%s' needs two ints or two colors, "
                               "found %s and %s" % (op, lt, rt))
            return BOOL
        # and / or
        if ERR not in (lt, rt) and (lt != BOOL or rt != BOOL):
            self._error(e, "operator '%s' needs bool operands, found %s and %s"
                        % (op, lt, rt))
        return BOOL


def analyze(program):
    """Run semantic analysis on a Program AST and return a SemanticResult."""
    return Analyzer().analyze(program)
