"""Compiler driver: runs every phase and collects the diagnostics.

Pipeline
    source -> lexer -> parser -> AST -> semantic analysis -> ICG -> runtime

Rules for moving from one phase to the next
  * the lexer and parser always run, even after errors (they recover)
  * semantic analysis runs only if lexing and parsing found no errors; the one
    exception is mode="panic", where it runs anyway so that the misleading
    follow-up errors caused by panic-mode recovery become visible
  * code generation and execution run only when there are no errors at all
    (warnings do not stop them)
"""

from dataclasses import dataclass
from typing import List, Optional

from . import astbuild, icg, lexer, parser, runtime, semantic
from .diagnostics import Diagnostic


@dataclass
class CompileResult:
    source: str
    mode: str
    lex: lexer.LexResult
    parse: parser.ParseResult
    ast: Optional[astbuild.Program]
    semantic: Optional[semantic.SemanticResult]
    icg: Optional[icg.ICGResult]
    run: Optional[runtime.RuntimeResult]
    diagnostics: List[Diagnostic]

    @property
    def errors(self):
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self):
        return [d for d in self.diagnostics if d.severity == "warning"]

    @property
    def ok(self):
        return not self.errors


def compile_source(source, mode="phrase", execute=True):
    """Compile (and by default run) PixelPen source text."""
    lex = lexer.tokenize(source)
    parsed = parser.parse(lex, mode)
    diagnostics = list(lex.errors) + list(parsed.errors)

    front_end_clean = not diagnostics
    ast = sem = code = result = None

    if front_end_clean or mode == "panic":
        try:
            ast = astbuild.build_ast(parsed.tree)
        except (AttributeError, IndexError, KeyError, TypeError):
            ast = None          # tree too damaged by recovery to translate
        if ast is not None:
            sem = semantic.analyze(ast)
            diagnostics.extend(sem.diagnostics)

    has_errors = any(d.severity == "error" for d in diagnostics)
    if ast is not None and sem is not None and not has_errors:
        code = icg.generate(ast, list(sem.symbols))
        if execute:
            result = runtime.run(code.quads, code.temps)
            if result.error is not None:
                diagnostics.append(result.error)
    return CompileResult(source, mode, lex, parsed, ast, sem, code, result,
                         diagnostics)
