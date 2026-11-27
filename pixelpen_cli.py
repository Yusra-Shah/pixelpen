"""Command line front end for the PixelPen compiler.

Usage
    python pixelpen_cli.py FILE.pp [--tokens] [--tree] [--trace] [--quads]
                                   [--panic] [--svg PATH]
    python pixelpen_cli.py --grammar

    --tokens   print the token table
    --tree     print the parse tree
    --trace    print the LL(1) parsing trace (stack, input, action)
    --quads    print the three-address code and the quadruple table
    --grammar  print productions, FIRST/FOLLOW, the LL(1) table and conflicts
    --panic    use panic-mode recovery only (to demonstrate misleading recovery)
    --svg PATH write the drawing to an SVG file

Diagnostics are always printed.  The exit status is 1 if any error was found.
"""

import argparse
import sys

from pixelpen import grammar, icg, parser, runtime
from pixelpen.compiler import compile_source


def print_tokens(result):
    print("TOKENS (%d)" % len(result.lex.tokens))
    print("%4s  %5s %4s  %-9s %s" % ("#", "line", "col", "kind", "lexeme"))
    for i, t in enumerate(result.lex.tokens + [result.lex.eof], 1):
        flag = "   <- error" if t.error else ""
        print("%4d  %5d %4d  %-9s %s%s" % (i, t.line, t.col, t.kind,
                                           t.lexeme or "(end)", flag))


def print_diagnostics(path, result):
    if not result.diagnostics:
        print("No errors or warnings.")
        return
    for d in result.diagnostics:
        print("%s:%d:%d: %s (%s): %s" % (path, d.line, d.col, d.severity,
                                         d.phase, d.message))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="PixelPen compiler and interpreter")
    ap.add_argument("file", nargs="?", help="PixelPen source file (.pp)")
    ap.add_argument("--tokens", action="store_true")
    ap.add_argument("--tree", action="store_true")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--quads", action="store_true")
    ap.add_argument("--grammar", action="store_true")
    ap.add_argument("--panic", action="store_true")
    ap.add_argument("--svg", metavar="PATH")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if args.grammar:
        print(grammar.format_all(grammar.get_grammar()))
        if not args.file:
            return 0
    if not args.file:
        ap.error("a source file is required (or use --grammar)")

    with open(args.file, "r", encoding="utf-8") as handle:
        source = handle.read()
    mode = "panic" if args.panic else "phrase"
    result = compile_source(source, mode)

    if args.tokens:
        print_tokens(result)
        print()
    if args.tree:
        print("PARSE TREE")
        print(parser.format_tree(result.parse.tree))
        print()
    if args.trace:
        print("LL(1) TRACE (%s recovery)" % mode)
        print(parser.format_trace(result.parse.trace))
        print()
    if args.quads:
        if result.icg is None:
            print("No code generated (fix the errors first).")
        else:
            print("THREE-ADDRESS CODE")
            print(icg.format_listing(result.icg.quads))
            print()
            print("QUADRUPLES")
            print(icg.format_quad_table(result.icg.quads))
        print()

    print_diagnostics(args.file, result)

    if result.run is not None:
        run = result.run
        print("Executed %d instructions, %d drawing operations."
              % (run.steps, len(run.draws)))
        if run.variables:
            print("Final values: " + ", ".join(
                "%s = %s" % (k, runtime.show(v))
                for k, v in run.variables.items()))
        if args.svg:
            with open(args.svg, "w", encoding="utf-8") as handle:
                handle.write(runtime.to_svg(run.draws))
            print("SVG written to %s" % args.svg)
    elif args.svg:
        print("No SVG written: the program was not executed.")
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
