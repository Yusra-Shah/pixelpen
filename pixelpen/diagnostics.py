"""Shared diagnostic record used by every compiler phase."""

from dataclasses import dataclass

PHASES = ("lexical", "syntax", "semantic", "runtime")


@dataclass(frozen=True)
class Diagnostic:
    """One message produced by a phase.

    phase    -- 'lexical', 'syntax', 'semantic' or 'runtime'
    line/col -- 1-based position in the source text
    severity -- 'error' or 'warning'
    """

    phase: str
    line: int
    col: int
    message: str
    severity: str = "error"

    def __str__(self):
        return "%s %s at line %d, col %d: %s" % (
            self.phase, self.severity, self.line, self.col, self.message)
