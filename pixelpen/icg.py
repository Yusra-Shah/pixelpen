"""Phase 5a: intermediate code generation (three-address code as quadruples).

The generator follows a syntax-directed translation scheme:

  * an expression returns an ADDRESS (a constant, a variable name or a temp);
    sub-expressions are generated first, then a new temp is allocated
        point (a, b)   ->  t = mkpoint a, b
        - a            ->  t = minus a
        a op b         ->  t = a op b
  * a condition B is translated into JUMPING CODE with inherited labels
    B.true and B.false; and / or / not short-circuit:
        B1 or B2   B1.true = B.true,  B1.false = new label
        B1 and B2  B1.true = new label, B1.false = B.false
        not B1     swap B.true and B.false
        a rel b    if a rel b goto B.true ; goto B.false
  * every statement receives an inherited label S.next (where control goes
    when the statement is finished)
        if (B) S1            B.true = new, B.false = S.next, S1.next = S.next
        if (B) S1 else S2    B.true = new, B.false = new, a 'goto S.next'
                             separates the two branches
        while (B) S1         begin = new, B.true = new, B.false = S.next,
                             S1.next = begin, 'goto begin' after the body
        repeat E S1          the count is evaluated once into a temp, a counter
                             temp starts at 0; at the begin label
                             'if counter >= count goto S.next'; the body ends
                             at a step label, then 'counter = counter + 1' and
                             'goto begin'
  * commands become 'param ...' instructions followed by 'call name, n'
  * the program ends with the label of the last S.next and 'halt'

A clean-up pass then removes labels nothing jumps to, merges labels that sit
on the same instruction, and renumbers the survivors L1, L2, ... in order of
appearance.
"""

from . import astbuild as A

ARITH = ("+", "-", "*", "/", "%")


class Quad:
    """One quadruple (op, arg1, arg2, result) plus an optional label.

    op values: '=' copy, '+ - * / %', 'minus', 'mkpoint', 'if<' 'if>=' ...
    (conditional jump; result is the target label), 'goto', 'param', 'call'
    (arg1 = name, arg2 = number of arguments), 'halt', and during generation
    'label' (removed by the clean-up pass).
    """

    __slots__ = ("op", "arg1", "arg2", "result", "label", "line")

    def __init__(self, op, arg1=None, arg2=None, result=None, line=0):
        self.op = op
        self.arg1 = arg1
        self.arg2 = arg2
        self.result = result
        self.label = None
        self.line = line

    def body(self):
        """The instruction text without its label."""
        op = self.op
        if op == "=":
            return "%s = %s" % (self.result, self.arg1)
        if op in ARITH:
            return "%s = %s %s %s" % (self.result, self.arg1, op, self.arg2)
        if op == "minus":
            return "%s = minus %s" % (self.result, self.arg1)
        if op == "mkpoint":
            return "%s = mkpoint %s, %s" % (self.result, self.arg1, self.arg2)
        if op.startswith("if"):
            return "if %s %s %s goto %s" % (self.arg1, op[2:], self.arg2,
                                            self.result)
        if op == "goto":
            return "goto %s" % self.result
        if op == "param":
            return "param %s" % self.arg1
        if op == "call":
            return "call %s, %s" % (self.arg1, self.arg2)
        if op == "halt":
            return "halt"
        return "%s %s %s %s" % (op, self.arg1, self.arg2, self.result)

    def text(self):
        """The instruction as printed in the listing, label included."""
        if self.label:
            return "%s: %s" % (self.label, self.body())
        return self.body()

    def __repr__(self):
        return "Quad(%s)" % self.text()


class ICGResult:
    def __init__(self, quads, temps, labels):
        self.quads = quads
        self.temps = temps          # temp names in order of creation
        self.labels = labels        # final label names in order L1, L2, ...


class CodeGenerator:
    def __init__(self, reserved_names=()):
        self.code = []
        self.reserved = set(reserved_names)
        self.temps = []
        self.label_count = 0
        self.line = 0

    # -- low-level helpers ---------------------------------------------------

    def new_temp(self):
        n = len(self.temps) + 1
        while "t%d" % n in self.reserved:       # never clash with a variable
            n += 1
        name = "t%d" % n
        self.reserved.add(name)
        self.temps.append(name)
        return name

    def new_label(self):
        self.label_count += 1
        return "#%d" % self.label_count         # internal id, renamed later

    def emit(self, op, arg1=None, arg2=None, result=None, line=None):
        self.code.append(Quad(op, arg1, arg2, result,
                              self.line if line is None else line))

    def place(self, label):
        self.emit("label", result=label)

    # -- program and statements ------------------------------------------------

    def generate(self, program):
        end = self.new_label()
        self.block(program.stmts, end)
        self.place(end)
        self.emit("halt")
        return self._clean_up()

    def block(self, stmts, next_label):
        for i, stmt in enumerate(stmts):
            if stmt is None:
                continue
            if i == len(stmts) - 1:
                self.stmt(stmt, next_label)
            else:
                mid = self.new_label()
                self.stmt(stmt, mid)
                self.place(mid)

    def stmt(self, s, next_label):
        self.line = s.line
        getattr(self, "s_" + type(s).__name__)(s, next_label)

    def s_Block(self, s, nxt):
        self.block(s.stmts, nxt)

    def s_Decl(self, s, nxt):
        addr = self.expr(s.init)
        self.emit("=", addr, None, s.name, line=s.line)

    def s_Assign(self, s, nxt):
        addr = self.expr(s.value)
        self.emit("=", addr, None, s.name, line=s.line)

    def s_Command(self, s, nxt):
        if s.arg is None:
            self.emit("call", s.name, 0)
            return
        addr = self.expr(s.arg)
        self.line = s.line
        self.emit("param", addr)
        self.emit("call", s.name, 1)

    def s_Shape(self, s, nxt):
        first = self.expr(s.first)
        second = self.expr(s.second)
        self.line = s.line
        self.emit("param", first)
        self.emit("param", second)
        self.emit("call", s.kind, 2)

    def s_Repeat(self, s, nxt):
        count = self.expr(s.count)
        self.line = s.line
        if count not in self.temps:           # snapshot constants/variables
            snapshot = self.new_temp()
            self.emit("=", count, None, snapshot)
            count = snapshot
        counter = self.new_temp()
        self.emit("=", "0", None, counter)
        begin, step = self.new_label(), self.new_label()
        self.place(begin)
        self.emit("if>=", counter, count, nxt)
        self.stmt(s.body, step)
        self.line = s.line
        self.place(step)
        self.emit("+", counter, "1", counter)
        self.emit("goto", result=begin)

    def s_While(self, s, nxt):
        begin, body = self.new_label(), self.new_label()
        self.place(begin)
        self.cond(s.cond, body, nxt)
        self.place(body)
        self.stmt(s.body, begin)
        self.line = s.line
        self.emit("goto", result=begin)

    def s_If(self, s, nxt):
        yes = self.new_label()
        if s.otherwise is None:
            self.cond(s.cond, yes, nxt)
            self.place(yes)
            self.stmt(s.then, nxt)
        else:
            no = self.new_label()
            self.cond(s.cond, yes, no)
            self.place(yes)
            self.stmt(s.then, nxt)
            self.emit("goto", result=nxt)
            self.place(no)
            self.stmt(s.otherwise, nxt)

    # -- conditions (jumping code) ----------------------------------------------

    def cond(self, b, true_label, false_label):
        if isinstance(b, A.Unary) and b.op == "not":
            self.cond(b.operand, false_label, true_label)
        elif isinstance(b, A.Binary) and b.op == "and":
            mid = self.new_label()
            self.cond(b.left, mid, false_label)
            self.place(mid)
            self.cond(b.right, true_label, false_label)
        elif isinstance(b, A.Binary) and b.op == "or":
            mid = self.new_label()
            self.cond(b.left, true_label, mid)
            self.place(mid)
            self.cond(b.right, true_label, false_label)
        elif isinstance(b, A.Binary):
            left = self.expr(b.left)
            right = self.expr(b.right)
            self.emit("if" + b.op, left, right, true_label, line=b.line)
            self.emit("goto", result=false_label, line=b.line)
        else:
            raise ValueError("not a condition: %r" % (b,))

    # -- expressions --------------------------------------------------------------

    def expr(self, e):
        if isinstance(e, A.Num):
            return str(e.value)
        if isinstance(e, A.Hex):
            return e.value
        if isinstance(e, A.Var):
            return e.name
        if isinstance(e, A.Point):
            x = self.expr(e.x)
            y = self.expr(e.y)
            t = self.new_temp()
            self.emit("mkpoint", x, y, t, line=e.line)
            return t
        if isinstance(e, A.Unary) and e.op == "-":
            a = self.expr(e.operand)
            t = self.new_temp()
            self.emit("minus", a, None, t, line=e.line)
            return t
        if isinstance(e, A.Binary) and e.op in ARITH:
            left = self.expr(e.left)
            right = self.expr(e.right)
            t = self.new_temp()
            self.emit(e.op, left, right, t, line=e.line)
            return t
        raise ValueError("not a value expression: %r" % (e,))

    # -- clean-up: drop, merge and renumber labels ---------------------------------

    def _clean_up(self):
        referenced = {q.result for q in self.code
                      if q.op == "goto" or q.op.startswith("if")}
        real = []
        pending = []
        alias = {}
        for q in self.code:
            if q.op == "label":
                if q.result in referenced:
                    pending.append(q.result)
                continue
            if pending:
                for other in pending[1:]:
                    alias[other] = pending[0]
                q.label = pending[0]
                pending = []
            real.append(q)
        names = {}
        labels = []
        for q in real:
            if q.label:
                names[q.label] = "L%d" % (len(names) + 1)
                labels.append(names[q.label])
        for old, canonical in alias.items():
            names[old] = names[canonical]
        for q in real:
            if q.label:
                q.label = names[q.label]
            if q.op == "goto" or q.op.startswith("if"):
                q.result = names[q.result]
        return ICGResult(real, self.temps, labels)


def generate(program, reserved_names=()):
    """Generate quadruples for a type-checked Program AST."""
    return CodeGenerator(reserved_names).generate(program)


def format_listing(quads):
    """Numbered three-address code listing (instruction numbers from 1)."""
    return "\n".join("%3d  %s" % (i + 1, q.text()) for i, q in enumerate(quads))


def format_quad_table(quads):
    """Quadruple table: index, label, op, arg1, arg2, result."""
    rows = ["%3s  %-5s %-8s %-10s %-10s %s" % ("#", "label", "op", "arg1",
                                               "arg2", "result")]
    for i, q in enumerate(quads):
        rows.append("%3d  %-5s %-8s %-10s %-10s %s" % (
            i + 1, q.label or "-", q.op,
            q.arg1 if q.arg1 is not None else "-",
            q.arg2 if q.arg2 is not None else "-",
            q.result if q.result is not None else "-"))
    return "\n".join(rows)
