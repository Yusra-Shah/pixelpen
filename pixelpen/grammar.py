"""Phase 2: the grammar, FIRST/FOLLOW sets and the LL(1) parsing table.

Everything is computed from the production list below; nothing is typed in by
hand.  Building the table finds exactly one conflict, M[ElsePart, else], the
classic dangling else.  It is resolved by keeping ElsePart -> else Stmt, so an
else binds to the nearest unmatched if.

Symbol conventions
  * nonterminals are the left-hand sides of the productions ("E", "E'", ...)
  * every other symbol is a terminal ('id', 'num', 'hex', 'relop', keywords
    and punctuation, exactly as the lexer names them)
  * EPS is the empty string marker and END is the end-of-input marker
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

EPS = "eps"
END = "$"
START_SYMBOL = "Program"

# Each entry is "LHS -> alternative | alternative"; 'eps' is the empty string.
_GRAMMAR_TEXT = """
Program    -> StmtList
StmtList   -> Stmt StmtList | eps
Stmt       -> Decl | Assign | Command | Shape | RepeatStmt | WhileStmt | IfStmt | Block
Decl       -> Type id = E ;
Type       -> int | color | point
Assign     -> id = E ;
Command    -> forward E ; | turn E ; | moveto E ; | penup ; | pendown ; | pencolor E ;
Shape      -> circle E , E ; | square E , E ; | line E , E ;
RepeatStmt -> repeat E Block
WhileStmt  -> while ( E ) Block
IfStmt     -> if ( E ) Stmt ElsePart
ElsePart   -> else Stmt | eps
Block      -> { StmtList }
E          -> T E'
E'         -> or T E' | eps
T          -> N T'
T'         -> and N T' | eps
N          -> not N | R
R          -> A R'
R'         -> relop A | eps
A          -> M A'
A'         -> + M A' | - M A' | eps
M          -> U M'
M'         -> * U M' | / U M' | % U M' | eps
U          -> - U | F
F          -> num | hex | id | ( E F'
F'         -> , E ) | )
"""


@dataclass(frozen=True)
class Production:
    """Production number (1-based), left side and right side (tuple)."""

    num: int
    lhs: str
    rhs: Tuple[str, ...]

    @property
    def is_epsilon(self):
        return self.rhs == (EPS,)

    def __str__(self):
        return "%s -> %s" % (self.lhs, " ".join(self.rhs))


@dataclass
class Conflict:
    """Two productions competing for one table cell."""

    nonterminal: str
    terminal: str
    productions: List[Production]
    resolved_with: Production = None
    reason: str = ""


def parse_grammar_text(text):
    """Turn the grammar text into a numbered list of Production objects."""
    productions = []
    for raw in text.strip().splitlines():
        lhs, _, right = raw.partition("->")
        lhs = lhs.strip()
        for alternative in right.split("|"):
            symbols = tuple(alternative.split())
            productions.append(Production(len(productions) + 1, lhs, symbols))
    return productions


class Grammar:
    """Productions plus FIRST, FOLLOW, the LL(1) table and its conflicts."""

    def __init__(self, text=_GRAMMAR_TEXT):
        self.productions = parse_grammar_text(text)
        self.start = self.productions[0].lhs
        self.nonterminals = []
        for p in self.productions:
            if p.lhs not in self.nonterminals:
                self.nonterminals.append(p.lhs)
        nt_set = set(self.nonterminals)
        self.terminals = []
        for p in self.productions:
            for s in p.rhs:
                if s != EPS and s not in nt_set and s not in self.terminals:
                    self.terminals.append(s)
        self.by_lhs = {nt: [p for p in self.productions if p.lhs == nt]
                       for nt in self.nonterminals}
        self.first = self._compute_first()
        self.follow = self._compute_follow()
        self.table, self.conflicts = self._build_table()

    # -- predicates ------------------------------------------------------

    def is_nonterminal(self, symbol):
        return symbol in self.by_lhs

    def is_nullable(self, nonterminal):
        return EPS in self.first[nonterminal]

    # -- FIRST -------------------------------------------------------------

    def first_of_sequence(self, symbols):
        """FIRST of a string of symbols; contains EPS if all can vanish."""
        result = set()
        for s in symbols:
            if s == EPS:
                continue
            if self.is_nonterminal(s):
                result |= self.first[s] - {EPS}
                if EPS not in self.first[s]:
                    return result
            else:
                result.add(s)
                return result
        result.add(EPS)
        return result

    def _compute_first(self):
        first = {nt: set() for nt in self.nonterminals}
        changed = True
        while changed:
            changed = False
            for p in self.productions:
                before = len(first[p.lhs])
                # FIRST(rhs) computed with the current approximation
                add = set()
                nullable_so_far = True
                for s in p.rhs:
                    if s == EPS:
                        continue
                    if s in first:
                        add |= first[s] - {EPS}
                        if EPS not in first[s]:
                            nullable_so_far = False
                            break
                    else:
                        add.add(s)
                        nullable_so_far = False
                        break
                if nullable_so_far:
                    add.add(EPS)
                first[p.lhs] |= add
                if len(first[p.lhs]) != before:
                    changed = True
        return first

    # -- FOLLOW ------------------------------------------------------------

    def _compute_follow(self):
        follow = {nt: set() for nt in self.nonterminals}
        follow[self.start].add(END)
        changed = True
        while changed:
            changed = False
            for p in self.productions:
                for i, s in enumerate(p.rhs):
                    if s not in follow:
                        continue
                    before = len(follow[s])
                    rest = self.first_of_sequence(p.rhs[i + 1:])
                    follow[s] |= rest - {EPS}
                    if EPS in rest:
                        follow[s] |= follow[p.lhs]
                    if len(follow[s]) != before:
                        changed = True
        return follow

    # -- LL(1) table -------------------------------------------------------

    def _build_table(self):
        table: Dict[Tuple[str, str], Production] = {}
        conflicts: Dict[Tuple[str, str], Conflict] = {}

        def put(nt, terminal, production):
            key = (nt, terminal)
            if key not in table:
                table[key] = production
                return
            if table[key] is production:
                return
            if key not in conflicts:
                conflicts[key] = Conflict(nt, terminal, [table[key]])
            conflicts[key].productions.append(production)

        for p in self.productions:
            rhs_first = self.first_of_sequence(p.rhs)
            for t in rhs_first - {EPS}:
                put(p.lhs, t, p)
            if EPS in rhs_first:
                for t in self.follow[p.lhs]:
                    put(p.lhs, t, p)

        # Resolution: prefer the non-empty production (shift preference).
        # For M[ElsePart, else] this keeps  ElsePart -> else Stmt.
        for key, conflict in conflicts.items():
            non_empty = [p for p in conflict.productions if not p.is_epsilon]
            chosen = non_empty[0] if non_empty else conflict.productions[0]
            conflict.resolved_with = chosen
            conflict.reason = ("keep '%s' so that else binds to the nearest "
                               "if" % chosen)
            table[key] = chosen
        return table, list(conflicts.values())

    def lookup(self, nonterminal, terminal):
        """The production for table cell M[nonterminal, terminal] or None."""
        return self.table.get((nonterminal, terminal))

    def expected_terminals(self, nonterminal):
        """Terminals with a non-empty table cell in the row of nonterminal."""
        row = [t for t in self.terminals + [END]
               if (nonterminal, t) in self.table]
        return row


_CACHE = []


def get_grammar():
    """Return the shared Grammar instance (built on first use)."""
    if not _CACHE:
        _CACHE.append(Grammar())
    return _CACHE[0]


# ---------------------------------------------------------------------------
# Text rendering (used by the CLI and the GUI)
# ---------------------------------------------------------------------------

def _sorted(symbols, grammar):
    order = grammar.terminals + [END, EPS]
    return sorted(symbols, key=order.index)


def format_productions(g):
    lines = []
    for p in g.productions:
        lines.append("%3d  %s" % (p.num, p))
    return "\n".join(lines)


def format_first_follow(g):
    width = max(len(nt) for nt in g.nonterminals)
    lines = ["%-*s  %-44s %s" % (width, "Symbol", "FIRST", "FOLLOW")]
    for nt in g.nonterminals:
        first = "{ " + ", ".join(_sorted(g.first[nt], g)) + " }"
        follow = "{ " + ", ".join(_sorted(g.follow[nt], g)) + " }"
        lines.append("%-*s  %-44s %s" % (width, nt, first, follow))
    return "\n".join(lines)


def table_rows(g):
    """Rows for display: header list and one list of cells per nonterminal."""
    columns = g.terminals + [END]
    header = ["M"] + columns
    rows = []
    for nt in g.nonterminals:
        row = [nt]
        for t in columns:
            p = g.table.get((nt, t))
            row.append(str(p.num) if p else "")
        rows.append(row)
    return header, rows


def format_table(g):
    header, rows = table_rows(g)
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]
    out = []
    for r in [header] + rows:
        out.append(" ".join(c.rjust(widths[i]) if i else c.ljust(widths[i])
                            for i, c in enumerate(r)))
    return "\n".join(out)


def format_conflicts(g):
    if not g.conflicts:
        return "No conflicts: the grammar is LL(1)."
    lines = ["%d conflict(s) found while filling the table:" % len(g.conflicts)]
    for c in g.conflicts:
        lines.append("  M[%s, %s] holds: %s" % (
            c.nonterminal, c.terminal,
            "  and  ".join("(%d) %s" % (p.num, p) for p in c.productions)))
        lines.append("  resolved: %s" % c.reason)
    return "\n".join(lines)


def format_summary(g):
    return "%d nonterminals, %d terminals, %d productions, %d conflict(s)" % (
        len(g.nonterminals), len(g.terminals), len(g.productions),
        len(g.conflicts))


def format_all(g):
    return "\n\n".join([
        "GRAMMAR (" + format_summary(g) + ")\n" + format_productions(g),
        "FIRST AND FOLLOW\n" + format_first_follow(g),
        "LL(1) TABLE (cell = production number)\n" + format_table(g),
        "CONFLICTS\n" + format_conflicts(g),
    ])
