# PixelPen

PixelPen is a small drawing language and a complete compiler for it, written for
the Compiler Construction lab (CSC-402, Sukkur IBA). A program moves a pen,
draws shapes and uses integers, colors and points. The compiler goes through
every classical phase and shows the result of each one.

Python 3.8 or newer, standard library only (tkinter for the GUI). The lexer
and the parser are written by hand.

## Running it

    python app.py                              # the GUI (F5 compiles and runs)
    python pixelpen_cli.py examples/01_case_study.pp --quads
    python pixelpen_cli.py examples/10_misleading_recovery.pp --panic
    python pixelpen_cli.py --grammar           # grammar, FIRST/FOLLOW, table
    python -m unittest discover tests          # run the test suite

CLI flags: `--tokens --tree --trace --quads --grammar --panic --svg PATH`.
The exit status is 1 when any error was found.

## Files

| File | Phase |
| --- | --- |
| `pixelpen/lexer.py` | Hand-written DFA scanner, longest match, keyword table, lexical error recovery |
| `pixelpen/grammar.py` | The 59 productions, FIRST, FOLLOW, LL(1) table, conflict detection and resolution |
| `pixelpen/parser.py` | Table-driven LL(1) parser with explicit stack, parse tree, trace and error recovery |
| `pixelpen/astbuild.py` | Parse tree to AST, folding the tail rules so operators are left associative |
| `pixelpen/semantic.py` | Symbol table and type checking |
| `pixelpen/icg.py` | Three-address code as quadruples, jumping code for conditions, label clean-up |
| `pixelpen/runtime.py` | Interpreter for the quadruples and SVG export |
| `pixelpen/compiler.py` | Runs all phases and collects diagnostics |
| `pixelpen/diagnostics.py` | The `Diagnostic` record (phase, line, col, message, severity) |
| `app.py` | Tkinter workbench |
| `pixelpen_cli.py` | Command line front end |
| `tests/test_pixelpen.py` | Unit tests for every phase, the examples and a GUI smoke test |
| `examples/*.pp` | Twelve programs (table below) |

## The language

Types: `int` (unsigned literals), `color` (`#RRGGBB`), `point` (`(x, y)`) and
`bool`, which only exists as the result of a comparison (no literals, no
variables). There is one global scope and every declaration needs an
initializer.

Keywords (19): `int color point forward turn moveto penup pendown pencolor
circle square line repeat while if else and or not`.

Statements:

    type id = E;      id = E;
    forward E;  turn E;  moveto E;  penup;  pendown;  pencolor E;
    circle P, R;  square P, S;  line P1, P2;
    repeat E { ... }  while (E) { ... }  if (E) Stmt [else Stmt]  { ... }

A comment is `#` followed by a space, a tab, a newline or the end of the file,
and runs to the end of the line.

Operator precedence, loosest to tightest: `or`, `and`, `not`, comparison
(`< > <= >= == !=`, not chainable), `+ -`, `* / %`, unary `-`.

Runtime model: the pen starts at (0, 0), facing up, pen down, black. The y axis
points up. `turn` is counterclockwise in degrees. `moveto` never draws.
`circle` and `square` are centered on the point. `/` truncates toward zero and
`%` keeps the sign of the left operand.

## Grammar facts (computed in code, checked by the tests)

27 nonterminals, 59 productions, 35 terminals, and exactly one table conflict,
`M[ElsePart, else]`. It is resolved by keeping `ElsePart -> else Stmt`, so an
`else` binds to the nearest `if`.

## Error handling

Lexer: `#FF57` and `#FF57331` are errors but a substitute HEX token is emitted;
`40px` is a malformed number (a NUM token is substituted); `#draw` skips the
rest of the line; `!` is only valid in `!=`.

Parser, in the default phrase-level mode:

1. Special messages: else without if, chained comparison (`M[T', relop]`),
   point with 3 coordinates, keyword used as a variable name,
   `unexpected number '90': missing operator?`, unmatched `}`.
2. A missing `;`, `)` or `}` is inserted when the lookahead is in FIRST(Stmt)
   or is `;` `}` `$`. For `;` and `)` the error is reported on the line of the
   previous token.
3. A loop body without braces is parsed as one statement (error production
   `Block -> Stmt`).
4. Panic mode as the fallback: skip tokens until a token in FIRST + FOLLOW of the
   current nonterminal, pop expression nonterminals on a FOLLOW token.
5. Cascade suppression: a new error is reported only after one token has been
   matched since the previous one.

`--panic` (or the Recovery dropdown) switches to panic mode only. Semantic
analysis normally runs only when parsing had no errors, but in panic mode it runs
anyway, which exposes the misleading follow-up errors (example 10).

## Three-address code

Expressions return an address and allocate a temp for every operator. Conditions
use jumping code with true and false labels, so `and`, `or` and `not` short
circuit. Each statement gets an inherited `S.next`. `repeat` evaluates its count
once into a temp and counts up with a second temp. Commands become `param`
instructions followed by `call name, n`; the program ends with `halt`. A final
pass removes labels nothing jumps to, merges labels on the same instruction and
renumbers the rest as L1, L2, ... in order of appearance.

The case study produces 28 instructions, labels L1 to L6, temps t1 to t6;
instruction 7 is `L1: if t2 >= t1 goto L6` and instruction 28 is `L6: halt`.

## Examples

| File | Shows |
| --- | --- |
| `01_case_study.pp` | The report's program: 57 tokens, 28 instructions |
| `02_hexagon.pp` | `repeat` and `turn` |
| `03_while_spiral.pp` | `while` with `or` (short-circuit jumping code) |
| `04_nested_stars.pp` | Nested loops and the dangling else |
| `05_points_lines.pp` | Points, lines, `moveto` |
| `06_boundary_cases.pp` | Edge cases, one warning (`repeat 0`) |
| `07_lexical_errors.pp` | Six lexical errors |
| `08_syntax_errors.pp` | Ten syntax errors, each reported once |
| `09_semantic_errors.pp` | Sixteen semantic errors and one warning |
| `10_misleading_recovery.pp` | Phrase-level: one error. Panic: a false "'c' is not declared" |
| `11_runtime_errors.pp` | Division by zero at run time |
| `12_infinite_loop.pp` | Stopped by the 200000-instruction limit |

## Design decisions worth knowing for the viva

* `penup` only suppresses the trail left by `forward`. `circle`, `square` and
  `line` are explicit drawing commands and always draw.
* `circle`, `square` and `line` never move the pen or change its heading.
* A variable that is declared inside a branch that never ran has no value; reading
  it is a runtime error (`variable 'b' has no value yet`).
* A negative `repeat` count runs zero times; only a constant `repeat 0` gets a
  compile-time warning.
* Compiler temps are named t1, t2, ... and skip any name the program already uses.
* The lexer returns the tokens without the end marker (57 for the case study);
  `LexResult.stream()` appends the `$` token for the parser.
