"""Phase 1: the lexical analyser (scanner).

The scanner is a hand-written DFA.  The transition table is built once by
_build_dfa(); the scanning loop walks the table from the START state, remembers
the last accepting state it passed (longest match), and falls back to that
position when the automaton gets stuck.

Identifiers and keywords share one DFA path: the scanner matches an ID and
then looks the lexeme up in the keyword table.

Lexical errors never stop the scan.  Where possible a substitute token is
emitted so that the parser can keep going:

  '#FF57'    -> error, but an (error) HEX token is substituted
  '40px'     -> error, but a NUM token (value 40) is substituted
  '#draw'    -> error, the rest of the line is skipped
  '!'        -> error ('!' is only valid inside '!=')
  other char -> error, the character is skipped
"""

from dataclasses import dataclass, field
from typing import List

from .diagnostics import Diagnostic

KEYWORDS = (
    "int", "color", "point",
    "forward", "turn", "moveto", "penup", "pendown", "pencolor",
    "circle", "square", "line",
    "repeat", "while", "if", "else",
    "and", "or", "not",
)
KEYWORD_SET = frozenset(KEYWORDS)

LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
DIGITS = frozenset("0123456789")
HEXDIGITS = frozenset("0123456789abcdefABCDEF")
ALNUM = LETTERS | DIGITS
SPACES = frozenset(" \t\r\n")

EOF_KIND = "$"


@dataclass
class Token:
    """A lexeme with its grammar terminal name and source position.

    kind   -- terminal name used by the grammar: 'id', 'num', 'hex', 'relop',
              a keyword, a punctuation character, or '$' for end of input
    value  -- int for num, upper-case '#RRGGBB' text for hex, else None
    error  -- True for a substitute token created after a lexical error
    """

    kind: str
    lexeme: str
    line: int
    col: int
    value: object = None
    error: bool = False

    @property
    def end_col(self):
        return self.col + len(self.lexeme)


@dataclass
class LexResult:
    """Everything the scanner produces."""

    tokens: List[Token]                       # without the end marker
    errors: List[Diagnostic]
    eof: Token
    comments: List[tuple] = field(default_factory=list)   # (line, col, length)

    def stream(self):
        """The token list followed by the '$' end marker (parser input)."""
        return self.tokens + [self.eof]


def _build_dfa():
    """Return (transitions, accepting) for the scanner DFA.

    transitions maps (state, character) to the next state;
    accepting maps an accepting state to the token kind it recognises.
    """
    trans = {}
    accept = {}

    def add(state, chars, nxt):
        for ch in chars:
            trans[(state, ch)] = nxt

    # identifiers and keywords:  letter (letter | digit)*
    add("START", LETTERS, "ID")
    add("ID", ALNUM, "ID")
    accept["ID"] = "id"

    # unsigned integers:  digit+
    add("START", DIGITS, "NUM")
    add("NUM", DIGITS, "NUM")
    accept["NUM"] = "num"

    # colour literals:  '#' followed by exactly six hex digits
    add("START", "#", "HASH")
    previous = "HASH"
    for i in range(1, 7):
        add(previous, HEXDIGITS, "H%d" % i)
        previous = "H%d" % i
    accept["H6"] = "hex"

    # relational operators and assignment
    add("START", "<", "LT")
    add("LT", "=", "LE")
    add("START", ">", "GT")
    add("GT", "=", "GE")
    add("START", "=", "EQ")
    add("EQ", "=", "EQEQ")
    add("START", "!", "BANG")          # not accepting: '!' alone is an error
    add("BANG", "=", "NE")
    for state in ("LT", "LE", "GT", "GE", "EQEQ", "NE"):
        accept[state] = "relop"
    accept["EQ"] = "="

    # single-character tokens
    for ch in "+-*/%,;(){}":
        add("START", ch, "P" + ch)
        accept["P" + ch] = ch

    return trans, accept


_TRANS, _ACCEPT = _build_dfa()


class Lexer:
    """Scans a source string into tokens (see the module docstring)."""

    def __init__(self, source):
        self.src = source
        self.n = len(source)
        self.pos = 0
        self.line = 1
        self.line_start = 0
        self.tokens = []
        self.errors = []
        self.comments = []

    # -- helpers ---------------------------------------------------------

    def _col(self, pos=None):
        return (self.pos if pos is None else pos) - self.line_start + 1

    def _error(self, col, message):
        self.errors.append(Diagnostic("lexical", self.line, col, message))

    def _emit(self, kind, lexeme, col, value=None, error=False):
        self.tokens.append(Token(kind, lexeme, self.line, col, value, error))

    def _longest_match(self):
        """Run the DFA from self.pos; return (kind, end) or None."""
        state = "START"
        i = self.pos
        last = None
        while i < self.n:
            state = _TRANS.get((state, self.src[i]))
            if state is None:
                break
            i += 1
            if state in _ACCEPT:
                last = (_ACCEPT[state], i)
        return last

    def _skip_to_end_of_line(self):
        while self.pos < self.n and self.src[self.pos] != "\n":
            self.pos += 1

    def _alnum_run_end(self, start):
        i = start
        while i < self.n and self.src[i] in ALNUM:
            i += 1
        return i

    # -- error handling for '#' --------------------------------------------

    def _bad_hash(self):
        """Handle '#' that is neither a comment nor a valid colour."""
        col = self._col()
        end = self._alnum_run_end(self.pos + 1)
        run = self.src[self.pos + 1:end]
        if run and all(c in HEXDIGITS for c in run):
            lexeme = self.src[self.pos:end]
            self._error(col, "invalid color '%s': a color needs exactly 6 hex "
                             "digits, found %d" % (lexeme, len(run)))
            self._emit("hex", lexeme, col, value=lexeme.upper(), error=True)
            self.pos = end
        else:
            shown = self.src[self.pos:end] if run else "#"
            self._error(col, "invalid '%s': '#' starts a comment only when "
                             "followed by a space, or a color with 6 hex "
                             "digits; skipping the rest of the line" % shown)
            self._skip_to_end_of_line()

    # -- main loop -----------------------------------------------------------

    def tokenize(self):
        src = self.src
        while self.pos < self.n:
            ch = src[self.pos]
            if ch == "\n":
                self.pos += 1
                self.line += 1
                self.line_start = self.pos
            elif ch in " \t\r":
                self.pos += 1
            elif ch == "#" and (self.pos + 1 >= self.n
                                or src[self.pos + 1] in SPACES):
                start = self.pos
                self._skip_to_end_of_line()
                self.comments.append((self.line, self._col(start),
                                      self.pos - start))
            else:
                self._scan_token()
        eof = Token(EOF_KIND, "", self.line, self._col())
        return LexResult(self.tokens, self.errors, eof, self.comments)

    def _scan_token(self):
        src = self.src
        col = self._col()
        match = self._longest_match()
        if match is None:
            ch = src[self.pos]
            if ch == "#":
                self._bad_hash()
                return
            if ch == "!":
                self._error(col, "'!' is only valid as part of '!='")
            else:
                self._error(col, "unexpected character %r" % ch)
            self.pos += 1
            return

        kind, end = match
        lexeme = src[self.pos:end]
        if kind == "num" and end < self.n and src[end] in LETTERS:
            run_end = self._alnum_run_end(end)
            bad = src[self.pos:run_end]
            self._error(col, "malformed number '%s': identifiers cannot "
                             "start with a digit and numbers cannot have "
                             "letters" % bad)
            self._emit("num", bad, col, value=int(lexeme), error=True)
            self.pos = run_end
        elif kind == "hex" and end < self.n and src[end] in ALNUM:
            self._bad_hash()            # seven or more digits, or junk after
        else:
            value = None
            if kind == "id" and lexeme in KEYWORD_SET:
                kind = lexeme
            elif kind == "num":
                value = int(lexeme)
            elif kind == "hex":
                value = lexeme.upper()
            self._emit(kind, lexeme, col, value=value)
            self.pos = end


def tokenize(source):
    """Convenience wrapper: scan source and return a LexResult."""
    return Lexer(source).tokenize()
