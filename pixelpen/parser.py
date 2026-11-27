"""Phase 3: table-driven LL(1) parser with error recovery.

The parser keeps an explicit stack of parse-tree nodes.  At every step it looks
at the top symbol X and the lookahead token a:

  * X is a terminal      -> match it with a, or report a mismatch
  * X is a nonterminal   -> expand with M[X, a], or report a syntax error
  * X is '$' and a is '$' -> accept

Every step is recorded in a trace of (stack, input, action) rows.

Error recovery (mode="phrase", the default) uses these strategies in order:

  1. special messages for common mistakes
       - 'else' without 'if'            - chained comparison (M[T', relop])
       - point with 3+ coordinates      - keyword used as a variable name
       - "unexpected number '90': missing operator?"   (turn 60 90;)
  2. expression tails are popped silently when the next token clearly starts a
     new statement (so a missing ';' or ')' is then reported in one place)
  3. a missing expression is reported and its nonterminal popped
  4. error production  Block -> Stmt  for a loop body without braces
  5. phrase-level insertion of a missing ';' ')' or '}' when the lookahead is
     in FIRST(Stmt) or is ';' '}' '$'  (reported on the previous token's line
     for ';' and ')')
  6. panic mode: skip tokens until one in FIRST(X) + FOLLOW(X) (or a statement
     terminator when X is a terminal), then pop X if it still cannot proceed

Cascade suppression: a new error is reported only after at least one token has
been matched since the previous error.

mode="panic" switches off strategies 1 to 5 so that only panic mode is used.
That is useful to demonstrate how panic mode can recover misleadingly.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .diagnostics import Diagnostic
from .grammar import END, EPS, get_grammar
from .lexer import KEYWORD_SET, Token

EXPR_START = frozenset(["E", "T", "N", "R", "A", "M", "U", "F"])
EXPR_TAIL = frozenset(["E'", "T'", "R'", "A'", "M'"])
TERMINATORS = (";", ")", ",", "}", "$")


# ---------------------------------------------------------------------------
# Parse tree and trace records
# ---------------------------------------------------------------------------

class PTNode:
    """A parse-tree node.

    symbol    -- nonterminal name, terminal kind, or 'eps'
    token     -- the matched Token for a terminal leaf
    production-- the Production used to expand a nonterminal
    inserted  -- True for a token inserted by phrase-level recovery
    error_production -- True for the recovery rule  Block -> Stmt
    """

    __slots__ = ("symbol", "children", "token", "production", "parent",
                 "inserted", "error_production")

    def __init__(self, symbol, parent=None):
        self.symbol = symbol
        self.children = []
        self.token = None
        self.production = None
        self.parent = parent
        self.inserted = False
        self.error_production = False

    def label(self):
        if self.symbol == EPS:
            return "eps"
        if self.token is not None:
            if self.inserted:
                return "%s (inserted)" % self.token.kind
            return "%s '%s'" % (self.symbol, self.token.lexeme)
        if self.error_production:
            return "%s (error production: Block -> Stmt)" % self.symbol
        return self.symbol

    def __repr__(self):
        return "PTNode(%s)" % self.label()


@dataclass
class TraceStep:
    step: int
    stack: str      # bottom first, top of the stack is the rightmost symbol
    input: str      # remaining input
    action: str


@dataclass
class ParseResult:
    tree: PTNode
    trace: List[TraceStep]
    errors: List[Diagnostic]
    mode: str = "phrase"


def format_tree(root):
    """Indented text rendering of a parse tree (iterative, no recursion)."""
    lines = []
    todo = [(root, 0)]
    while todo:
        node, depth = todo.pop()
        lines.append("  " * depth + node.label())
        for child in reversed(node.children):
            todo.append((child, depth + 1))
    return "\n".join(lines)


def format_trace(trace):
    rows = ["%4s  %-46s %-34s %s" % ("step", "stack (top at right)",
                                     "input", "action")]
    for t in trace:
        stack = t.stack if len(t.stack) <= 46 else "..." + t.stack[-43:]
        rows.append("%4d  %-46s %-34s %s" % (t.step, stack, t.input, t.action))
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Helpers for messages
# ---------------------------------------------------------------------------

def describe(tok):
    """Human description of a token for error messages."""
    k = tok.kind
    if k == END:
        return "end of file"
    if k == "id":
        return "identifier '%s'" % tok.lexeme
    if k == "num":
        return "number '%s'" % tok.lexeme
    if k == "hex":
        return "color '%s'" % tok.lexeme
    if k == "relop":
        return "operator '%s'" % tok.lexeme
    if k in KEYWORD_SET:
        return "keyword '%s'" % k
    return "'%s'" % tok.lexeme


def _friendly(terminal):
    names = {"id": "identifier", "num": "number", "hex": "color",
             "relop": "comparison operator", END: "end of file"}
    return names.get(terminal, "'%s'" % terminal)


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens, mode="phrase", grammar=None):
        """tokens: list of Token ending with the '$' token (LexResult.stream())."""
        if mode not in ("phrase", "panic"):
            raise ValueError("mode must be 'phrase' or 'panic'")
        self.g = grammar or get_grammar()
        self.tokens = list(tokens)
        self.mode = mode
        self.i = 0
        self.stack: List[PTNode] = []
        self.trace: List[TraceStep] = []
        self.errors: List[Diagnostic] = []
        self.matched_since_error = True
        self.root: Optional[PTNode] = None
        self.first_stmt = self.g.first["Stmt"]

    # -- small accessors -----------------------------------------------------

    @property
    def tok(self):
        return self.tokens[self.i]

    @property
    def prev(self):
        return self.tokens[self.i - 1] if self.i > 0 else None

    def _starts_stmt(self, idx=None):
        """True if the token at idx clearly begins a new statement.

        An identifier only counts when it is followed by '=' (an assignment),
        because an identifier may also be a stray operand.
        """
        idx = self.i if idx is None else idx
        t = self.tokens[idx]
        if t.kind == "id":
            return idx + 1 < len(self.tokens) and self.tokens[idx + 1].kind == "="
        return t.kind in self.first_stmt

    def _after_prev(self):
        """Position just after the previous token (where ';' or ')' is missing)."""
        p = self.prev
        if p is None:
            return self.tok.line, self.tok.col
        return p.line, p.end_col

    def _missing_pos(self):
        """Position for a 'missing expression' report."""
        p = self.prev
        if p is not None and p.line < self.tok.line:
            return p.line, p.end_col
        return self.tok.line, self.tok.col

    # -- trace and error plumbing ----------------------------------------------

    def _log(self, action):
        stack = " ".join(n.symbol for n in self.stack)
        upcoming = [(t.lexeme if t.kind != END else "$")
                    for t in self.tokens[self.i:self.i + 8]]
        text = " ".join(upcoming)
        if self.i + 8 < len(self.tokens):
            text += " ..."
        self.trace.append(TraceStep(len(self.trace) + 1, stack, text, action))

    def _fail(self, message, line, col, recovery):
        """Report (unless suppressed) and log the error step.

        The caller then performs the recovery action without logging it again.
        """
        if self.matched_since_error:
            self.errors.append(Diagnostic("syntax", line, col, message))
            self._log("ERROR: %s; %s" % (message, recovery))
        else:
            self._log("error suppressed (cascade): %s; %s" % (message, recovery))
        self.matched_since_error = False

    # -- stack primitives ----------------------------------------------------

    def _expand(self, node, production, note=""):
        self._log("expand %s%s" % (production, note))
        children = [PTNode(s, node) for s in production.rhs]
        node.children = children
        node.production = production
        self.stack.pop()
        for child in reversed(children):
            if child.symbol != EPS:
                self.stack.append(child)

    def _match(self, node, log=True):
        tok = self.tok
        if log:
            self._log("match %s" % describe(tok))
        node.token = tok
        self.stack.pop()
        self.i += 1
        self.matched_since_error = True

    def _skip(self, log=True):
        """Discard the lookahead token (never the end marker)."""
        if self.tok.kind == END:
            return
        if log:
            self._log("skip %s" % describe(self.tok))
        self.i += 1

    def _pop(self, log_text=None):
        if log_text:
            self._log(log_text)
        self.stack.pop()

    # -- main loop -----------------------------------------------------------

    def parse(self):
        g = self.g
        bottom = PTNode(END)
        self.root = PTNode(g.start)
        self.stack = [bottom, self.root]
        limit = 200 * len(self.tokens) + 5000
        steps = 0
        while True:
            steps += 1
            if steps > limit:
                raise RuntimeError("parser made no progress (internal error)")
            node = self.stack[-1]
            x = node.symbol
            tok = self.tok
            a = tok.kind
            if x == END:
                if a == END:
                    self._log("accept")
                    break
                self._extra_tokens(node)
            elif not g.is_nonterminal(x):
                if x == a:
                    self._match(node)
                else:
                    self._handle_error(node, tok)
            else:
                production = g.lookup(x, a)
                if production is None:
                    self._handle_error(node, tok)
                else:
                    note = ""
                    if any(c.nonterminal == x and c.terminal == a
                           for c in g.conflicts):
                        note = "   [conflict: else binds to nearest if]"
                    self._expand(node, production, note)
        return ParseResult(self.root, self.trace, self.errors, self.mode)

    # -- extra tokens after the program ----------------------------------------

    def _extra_tokens(self, node):
        tok = self.tok
        if self.mode == "phrase" and tok.kind == "}":
            message = "unmatched '}': there is no open block to close"
        else:
            message = "unexpected %s after the end of the program" % describe(tok)
        self._fail(message, tok.line, tok.col, "skip it and keep parsing")
        self._skip(log=False)
        if self.tok.kind != END:
            extra = PTNode("StmtList", self.root)
            self.root.children.append(extra)
            self.stack.append(extra)

    # -- error dispatch ---------------------------------------------------------

    def _handle_error(self, node, tok):
        if self.mode == "phrase":
            for handler in (self._else_without_if,
                            self._chained_comparison,
                            self._point_arity,
                            self._keyword_as_name,
                            self._missing_operator,
                            self._silent_tail_pop,
                            self._missing_expression,
                            self._braceless_body,
                            self._insert_missing):
                if handler(node, tok):
                    return
        self._panic(node, tok)

    # -- phrase-level handlers (each returns True when it handled the error) --

    def _else_without_if(self, node, tok):
        if node.symbol == "StmtList" and tok.kind == "else":
            self._fail("'else' without a matching 'if'", tok.line, tok.col,
                       "discard 'else'")
            self._skip(log=False)
            return True
        return False

    def _chained_comparison(self, node, tok):
        # M[T', relop]: a second comparison right after a complete one
        if node.symbol != "T'" or tok.kind != "relop":
            return False
        self._fail("chained comparison: 'a < b < c' is not allowed; combine "
                   "comparisons with 'and' or 'or'", tok.line, tok.col,
                   "skip the extra comparison")
        sync = self.g.follow["T'"]
        depth = 0
        first = True
        while self.tok.kind != END:
            t = self.tok
            if depth == 0 and not first and (
                    t.kind in sync or t.kind == "}" or self._starts_stmt()):
                break
            if t.kind == "(":
                depth += 1
            elif t.kind == ")":
                if depth == 0:
                    break
                depth -= 1
            self._skip(log=not first)
            first = False
        return True

    def _point_arity(self, node, tok):
        parent = node.parent
        if not (node.symbol == ")" and tok.kind == "," and parent is not None
                and parent.symbol == "F'" and parent.production is not None
                and parent.production.rhs[0] == ","):
            return False
        # count the coordinates from the lookahead onwards
        depth, commas, j = 0, 0, self.i
        while j < len(self.tokens):
            k = self.tokens[j].kind
            if k in (";", "}", END):
                break
            if k == "(":
                depth += 1
            elif k == ")":
                if depth == 0:
                    break
                depth -= 1
            elif k == "," and depth == 0:
                commas += 1
            j += 1
        self._fail("a point has exactly 2 coordinates, found %d" % (2 + commas),
                   tok.line, tok.col, "skip the extra coordinates")
        depth = 0
        first = True
        while True:
            t = self.tok
            if t.kind in (";", "}", END):
                self._insert_token(node, ")", log="insert ')' to close the point")
                break
            if t.kind == "(":
                depth += 1
            elif t.kind == ")":
                if depth == 0:
                    self._match(node)
                    break
                depth -= 1
            self._skip(log=not first)
            first = False
        return True

    def _keyword_as_name(self, node, tok):
        x, a = node.symbol, tok.kind
        nxt = self.tokens[min(self.i + 1, len(self.tokens) - 1)]
        prev = self.prev
        as_declared_name = (x == "id" and a in KEYWORD_SET)
        as_operand = (x in EXPR_START and a in KEYWORD_SET
                      and a not in ("not", "and", "or")
                      and prev is not None and prev.line == tok.line
                      and nxt.kind in (";", ",", ")", "+", "-", "*", "/", "%",
                                       "relop", "and", "or", "{"))
        if as_declared_name or as_operand:
            self._fail("'%s' is a keyword and cannot be used as a variable "
                       "name" % a, tok.line, tok.col,
                       "treat it as an identifier")
            # replace the token in the stream and let the main loop continue
            self.tokens[self.i] = Token("id", tok.lexeme, tok.line, tok.col,
                                        error=True)
            return True
        keyword_target = (x in EXPR_START and a == "=" and prev is not None
                          and prev.kind in ("forward", "turn", "moveto",
                                            "pencolor", "circle", "square",
                                            "line", "repeat")
                          and node.parent is not None)
        if keyword_target:
            self._fail("'%s' is a keyword and cannot be used as a variable "
                       "name" % prev.kind, prev.line, prev.col,
                       "discard the statement")
            parent = node.parent
            while self.stack[-1].parent is parent:
                self.stack.pop()
            while self.tok.kind not in ("}", END):
                t = self.tok
                if t.kind == ";":
                    self._skip(log=False)
                    break
                if self._starts_stmt() and t is not tok:
                    break
                self._skip(log=False)
            return True
        return False

    def _missing_operator(self, node, tok):
        if (node.symbol in EXPR_TAIL and tok.kind in ("num", "hex", "id")
                and not self._starts_stmt()):
            self._fail("unexpected %s: missing operator?" % describe(tok),
                       tok.line, tok.col, "skip it")
            self._skip(log=False)
            return True
        return False

    def _silent_tail_pop(self, node, tok):
        """An expression ends here: the next token starts a new statement."""
        if node.symbol in EXPR_TAIL and (self._starts_stmt()
                                         or tok.kind in ("}", END)):
            self._pop("%s -> eps (expression ends before %s)"
                      % (node.symbol, describe(tok)))
            return True
        return False

    def _missing_expression(self, node, tok):
        x, a = node.symbol, tok.kind
        if x in EXPR_START and (
                a in TERMINATORS
                or (a in self.first_stmt and a not in self.g.first[x])):
            line, col = self._missing_pos()
            self._fail("expected an expression, found %s" % describe(tok),
                       line, col, "pop %s" % x)
            self._pop()
            return True
        return False

    def _braceless_body(self, node, tok):
        parent = node.parent
        if (node.symbol == "Block" and parent is not None
                and parent.symbol in ("RepeatStmt", "WhileStmt")
                and self._starts_stmt()):
            self._fail("the body of '%s' must be enclosed in '{' and '}'"
                       % parent.symbol.replace("Stmt", "").lower(),
                       tok.line, tok.col,
                       "error production Block -> Stmt (one statement)")
            body = PTNode("Stmt", node)
            node.children = [body]
            node.error_production = True
            self.stack.pop()
            self.stack.append(body)
            return True
        return False

    def _insert_token(self, node, kind, log=None):
        """Pop terminal node as if kind had been present in the input."""
        if log:
            self._log(log)
        line, col = self._after_prev() if kind != "}" else (self.tok.line,
                                                            self.tok.col)
        node.token = Token(kind, kind, line, col, error=True)
        node.inserted = True
        self.stack.pop()

    def _insert_missing(self, node, tok):
        x, a = node.symbol, tok.kind
        if x not in (";", ")", "}", "F'"):
            return False
        if not (a in self.first_stmt or a in (";", "}", END)):
            return False
        expected = ")" if x == "F'" else x
        if expected == "}":
            line, col = tok.line, tok.col
            message = ("missing '}' before the end of the file"
                       if a == END else "missing '}'")
        else:
            line, col = self._after_prev()
            message = "missing '%s'" % expected
        self._fail(message, line, col, "insert '%s'" % expected)
        if x == "F'":
            production = self.g.by_lhs["F'"][1]            # F' -> )
            leaf = PTNode(")", node)
            leaf.token = Token(")", ")", line, col, error=True)
            leaf.inserted = True
            node.children = [leaf]
            node.production = production
            self.stack.pop()
        else:
            self._insert_token(node, expected)
        return True

    # -- panic mode ----------------------------------------------------------------

    def _panic(self, node, tok):
        g = self.g
        x = node.symbol
        if g.is_nonterminal(x):
            if x in EXPR_START:
                expected = "an expression"
            else:
                names = [_friendly(t) for t in g.expected_terminals(x)]
                expected = ", ".join(names[:6]) + (", ..." if len(names) > 6 else "")
            message = "unexpected %s, expected %s" % (describe(tok), expected)
            sync = (g.first[x] - {EPS}) | g.follow[x] | {END}
        else:
            message = "expected '%s' but found %s" % (x, describe(tok))
            sync = {x, ";", "}", END}
        self._fail(message, tok.line, tok.col, "panic mode: skip to a sync token")
        first = True
        while self.tok.kind not in sync:
            self._skip(log=not first)
            first = False
        if g.is_nonterminal(x):
            if g.lookup(x, self.tok.kind) is None:
                self._pop("panic mode: pop %s" % x)
        elif self.tok.kind != x:
            self._pop("panic mode: pop '%s'" % x)


def parse(lex_result, mode="phrase"):
    """Parse a LexResult (or a token list ending in '$') and return a ParseResult."""
    tokens = lex_result.stream() if hasattr(lex_result, "stream") else lex_result
    return Parser(tokens, mode).parse()
