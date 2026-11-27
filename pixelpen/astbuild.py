"""Phase 4a: parse tree to abstract syntax tree (AST).

The LL(1) grammar has no left recursion, so left-associative operators appear
in the parse tree as "tail" rules:  E' -> or T E',  A' -> + M A'  and so on.
The builder folds each tail from left to right, so  a - b - c  becomes
(a - b) - c  and not  a - (b - c).

Every AST node carries the line and column of its most useful token (the
operator for binary expressions, the name for declarations and assignments).
"""

from .grammar import EPS


class Ast:
    """Base class: positional field values plus a source position."""

    fields = ()

    def __init__(self, *values, line=0, col=0):
        for name, value in zip(self.fields, values):
            setattr(self, name, value)
        self.line = line
        self.col = col

    def __repr__(self):
        inner = ", ".join("%s=%r" % (f, getattr(self, f)) for f in self.fields)
        return "%s(%s)" % (type(self).__name__, inner)


# -- statements --------------------------------------------------------------

class Program(Ast):
    fields = ("stmts",)


class Decl(Ast):                  # int x = E;     (line/col = the name)
    fields = ("type_name", "name", "init")


class Assign(Ast):                # x = E;
    fields = ("name", "value")


class Command(Ast):               # forward E; turn E; moveto E; pencolor E;
    fields = ("name", "arg")      # penup; pendown;  (arg is None)


class Shape(Ast):                 # circle P, R;  square P, S;  line P, Q;
    fields = ("kind", "first", "second")


class Repeat(Ast):
    fields = ("count", "body")


class While(Ast):
    fields = ("cond", "body")


class If(Ast):
    fields = ("cond", "then", "otherwise")      # otherwise may be None


class Block(Ast):
    fields = ("stmts",)


# -- expressions -------------------------------------------------------------

class Num(Ast):
    fields = ("value",)


class Hex(Ast):
    fields = ("value",)


class Var(Ast):
    fields = ("name",)


class Point(Ast):
    fields = ("x", "y")


class Binary(Ast):
    fields = ("op", "left", "right")


class Unary(Ast):
    fields = ("op", "operand")


# ---------------------------------------------------------------------------

def _real_children(node):
    return [c for c in node.children if c.symbol != EPS]


class AstBuilder:
    """Walks a parse tree (see parser.PTNode) and returns a Program node.

    The tree may be incomplete after error recovery; callers that build an AST
    from such a tree should be ready for an exception.
    """

    def build(self, root):
        stmts = []
        for child in root.children:
            if child.symbol == "StmtList":
                stmts.extend(self._stmt_list(child))
        return Program(stmts, line=1, col=1)

    # -- statements ------------------------------------------------------------

    def _stmt_list(self, node):
        stmts = []
        while node is not None and node.symbol == "StmtList":
            kids = _real_children(node)
            if not kids:
                break
            stmts.append(self._stmt(kids[0]))
            node = kids[1] if len(kids) > 1 else None
        return stmts

    def _stmt(self, node):
        inner = node.children[0]
        handler = getattr(self, "_" + inner.symbol)
        return handler(inner)

    @staticmethod
    def _tok(node):
        return node.token

    def _Decl(self, n):
        type_node, name, _eq, expr, _semi = n.children
        t = name.token
        return Decl(type_node.children[0].token.kind, t.lexeme,
                    self._expr(expr), line=t.line, col=t.col)

    def _Assign(self, n):
        name, _eq, expr, _semi = n.children
        t = name.token
        return Assign(t.lexeme, self._expr(expr), line=t.line, col=t.col)

    def _Command(self, n):
        kw = n.children[0].token
        arg = None
        if len(n.children) == 3:
            arg = self._expr(n.children[1])
        return Command(kw.kind, arg, line=kw.line, col=kw.col)

    def _Shape(self, n):
        kw = n.children[0].token
        return Shape(kw.kind, self._expr(n.children[1]),
                     self._expr(n.children[3]), line=kw.line, col=kw.col)

    def _RepeatStmt(self, n):
        kw = n.children[0].token
        return Repeat(self._expr(n.children[1]), self._Block(n.children[2]),
                      line=kw.line, col=kw.col)

    def _WhileStmt(self, n):
        kw = n.children[0].token
        return While(self._expr(n.children[2]), self._Block(n.children[4]),
                     line=kw.line, col=kw.col)

    def _IfStmt(self, n):
        kw = n.children[0].token
        cond = self._expr(n.children[2])
        then = self._stmt(n.children[4])
        else_part = _real_children(n.children[5])
        otherwise = self._stmt(else_part[1]) if else_part else None
        return If(cond, then, otherwise, line=kw.line, col=kw.col)

    def _Block(self, n):
        if n.error_production:                    # Block -> Stmt (recovery)
            stmt = self._stmt(n.children[0])
            return Block([stmt], line=stmt.line, col=stmt.col)
        open_brace = n.children[0].token
        stmts = self._stmt_list(n.children[1])
        return Block(stmts, line=open_brace.line, col=open_brace.col)

    # -- expressions -----------------------------------------------------------

    def _expr(self, node):
        handler = getattr(self, "_x_" + node.symbol.replace("'", "p"))
        return handler(node)

    def _fold(self, left, tail, operand):
        """Fold a tail rule  op operand tail  into left-associative nodes."""
        while tail is not None:
            kids = _real_children(tail)
            if not kids:
                break
            op = kids[0].token
            right = self._expr(kids[1])
            left = Binary(op.lexeme, left, right, line=op.line, col=op.col)
            tail = kids[2] if len(kids) > 2 else None
        return left

    def _x_E(self, n):
        return self._fold(self._expr(n.children[0]), n.children[1], "T")

    def _x_T(self, n):
        return self._fold(self._expr(n.children[0]), n.children[1], "N")

    def _x_N(self, n):
        kids = n.children
        if len(kids) == 2:                         # not N
            op = kids[0].token
            return Unary("not", self._expr(kids[1]), line=op.line, col=op.col)
        return self._expr(kids[0])

    def _x_R(self, n):
        return self._fold(self._expr(n.children[0]), n.children[1], "A")

    def _x_A(self, n):
        return self._fold(self._expr(n.children[0]), n.children[1], "M")

    def _x_M(self, n):
        return self._fold(self._expr(n.children[0]), n.children[1], "U")

    def _x_U(self, n):
        kids = n.children
        if len(kids) == 2:                         # - U
            op = kids[0].token
            return Unary("-", self._expr(kids[1]), line=op.line, col=op.col)
        return self._expr(kids[0])

    def _x_F(self, n):
        first = n.children[0]
        if first.symbol == "num":
            t = first.token
            return Num(t.value, line=t.line, col=t.col)
        if first.symbol == "hex":
            t = first.token
            return Hex(t.value, line=t.line, col=t.col)
        if first.symbol == "id":
            t = first.token
            return Var(t.lexeme, line=t.line, col=t.col)
        # ( E F'
        inner = self._expr(n.children[1])
        rest = _real_children(n.children[2])       # F' -> , E )   or   )
        if len(rest) == 3:
            second = self._expr(rest[1])
            return Point(inner, second, line=first.token.line,
                         col=first.token.col)
        return inner


def build_ast(parse_tree_root):
    """Convenience wrapper: parse tree root to a Program node."""
    return AstBuilder().build(parse_tree_root)


def dump(node, indent=0):
    """Readable indented text of an AST (used by tests and the CLI)."""
    pad = "  " * indent
    if isinstance(node, list):
        return "\n".join(dump(n, indent) for n in node)
    if not isinstance(node, Ast):
        return pad + repr(node)
    simple = [f for f in node.fields
              if not isinstance(getattr(node, f), (Ast, list))]
    head = pad + type(node).__name__
    if simple:
        head += " " + " ".join("%s=%r" % (f, getattr(node, f)) for f in simple)
    lines = [head]
    for f in node.fields:
        value = getattr(node, f)
        if isinstance(value, (Ast, list)) and value:
            lines.append(pad + "  " + f + ":")
            lines.append(dump(value, indent + 2))
    return "\n".join(lines)
