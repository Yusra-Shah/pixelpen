"""Unit tests for every PixelPen phase (run: python -m unittest discover tests)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pixelpen import lexer  # noqa: E402

CASE_STUDY = """# flower of squares and circles
int size = 20;
color petal = #FF5733;
pencolor petal;
repeat 6 {
    if (size > 30 and size < 100)
        square (0, 0), size;
    else
        circle (0, 0), size / 2;
    turn 60;
    size = size + 20;
}
"""


def kinds(source):
    return [t.kind for t in lexer.tokenize(source).tokens]


class LexerTests(unittest.TestCase):
    def test_keyword_table_has_19_entries(self):
        self.assertEqual(len(lexer.KEYWORDS), 19)

    def test_case_study_57_tokens_no_errors(self):
        res = lexer.tokenize(CASE_STUDY)
        self.assertEqual(len(res.tokens), 57)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.eof.kind, "$")

    def test_keywords_versus_identifiers(self):
        self.assertEqual(kinds("int integer circle circles"),
                         ["int", "id", "circle", "id"])

    def test_longest_match_relops(self):
        self.assertEqual(kinds("a<=b a<b a==b a=b a!=b a>=b a>b"),
                         ["id", "relop", "id", "id", "relop", "id",
                          "id", "relop", "id", "id", "=", "id",
                          "id", "relop", "id", "id", "relop", "id",
                          "id", "relop", "id"])
        lexemes = [t.lexeme for t in lexer.tokenize("<= == != >=").tokens]
        self.assertEqual(lexemes, ["<=", "==", "!=", ">="])

    def test_lone_bang_is_error(self):
        res = lexer.tokenize("x ! y")
        self.assertEqual(len(res.errors), 1)
        self.assertIn("'!'", res.errors[0].message)
        self.assertEqual([t.kind for t in res.tokens], ["id", "id"])

    def test_hex_literal(self):
        res = lexer.tokenize("#FF5733 #00aaFF")
        self.assertEqual(res.errors, [])
        self.assertEqual([t.value for t in res.tokens], ["#FF5733", "#00AAFF"])

    def test_short_hex_substitutes_token(self):
        res = lexer.tokenize("color c = #FF57;\nturn 1;")
        self.assertEqual(len(res.errors), 1)
        self.assertEqual(res.errors[0].line, 1)
        self.assertEqual(res.tokens[3].kind, "hex")
        self.assertTrue(res.tokens[3].error)
        self.assertEqual(res.tokens[4].kind, ";")      # scanning continued

    def test_long_hex_substitutes_token(self):
        res = lexer.tokenize("#FF57331;")
        self.assertEqual(len(res.errors), 1)
        self.assertEqual([t.kind for t in res.tokens], ["hex", ";"])

    def test_hash_word_skips_rest_of_line(self):
        res = lexer.tokenize("#draw the box 1 2 3\nturn 5;")
        self.assertEqual(len(res.errors), 1)
        self.assertEqual([t.kind for t in res.tokens], ["turn", "num", ";"])
        self.assertEqual(res.tokens[0].line, 2)

    def test_comments(self):
        res = lexer.tokenize("# one\n#\n#\ttab\nturn 1; # trailing\n# last")
        self.assertEqual(res.errors, [])
        self.assertEqual(len(res.tokens), 3)
        self.assertEqual(len(res.comments), 5)

    def test_comment_at_end_of_file(self):
        res = lexer.tokenize("turn 1;\n#")
        self.assertEqual(res.errors, [])
        self.assertEqual(len(res.tokens), 3)

    def test_malformed_number(self):
        res = lexer.tokenize("forward 40px;")
        self.assertEqual(len(res.errors), 1)
        self.assertIn("malformed number '40px'", res.errors[0].message)
        self.assertEqual([t.kind for t in res.tokens],
                         ["forward", "num", ";"])
        self.assertEqual(res.tokens[1].value, 40)

    def test_unexpected_character(self):
        res = lexer.tokenize("x @ y")
        self.assertEqual(len(res.errors), 1)
        self.assertEqual(res.errors[0].col, 3)

    def test_positions(self):
        res = lexer.tokenize("int a = 5;\n  turn a;")
        t = res.tokens
        self.assertEqual((t[0].line, t[0].col), (1, 1))
        self.assertEqual((t[1].line, t[1].col), (1, 5))
        self.assertEqual((t[5].line, t[5].col), (2, 3))     # 'turn'
        self.assertEqual((t[6].line, t[6].col), (2, 8))     # 'a'

    def test_crlf_input(self):
        res = lexer.tokenize("turn 1;\r\nturn 2;\r\n")
        self.assertEqual(res.errors, [])
        self.assertEqual(res.tokens[3].line, 2)


from pixelpen import grammar  # noqa: E402


class GrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = grammar.get_grammar()

    def test_counts(self):
        self.assertEqual(len(self.g.nonterminals), 27)
        self.assertEqual(len(self.g.productions), 59)

    def test_exactly_one_conflict_resolved_to_else(self):
        self.assertEqual(len(self.g.conflicts), 1)
        c = self.g.conflicts[0]
        self.assertEqual((c.nonterminal, c.terminal), ("ElsePart", "else"))
        self.assertEqual(len(c.productions), 2)
        self.assertEqual(str(self.g.lookup("ElsePart", "else")),
                         "ElsePart -> else Stmt")

    def test_first_sets(self):
        f = self.g.first
        self.assertEqual(f["Type"], {"int", "color", "point"})
        self.assertEqual(f["E'"], {"or", "eps"})
        self.assertEqual(f["M'"], {"*", "/", "%", "eps"})
        self.assertEqual(f["F"], {"num", "hex", "id", "("})
        self.assertEqual(f["R"], {"num", "hex", "id", "(", "-"})
        self.assertIn("not", f["N"])
        self.assertNotIn("not", f["R"])
        self.assertEqual(f["F'"], {",", ")"})

    def test_follow_sets(self):
        f = self.g.follow
        self.assertEqual(f["Program"], {"$"})
        self.assertEqual(f["E"], {";", ",", ")", "{"})
        self.assertEqual(f["T'"], {";", ",", ")", "{", "or"})
        self.assertIn("else", f["Stmt"])
        self.assertIn("}", f["StmtList"])
        self.assertEqual(f["Type"], {"id"})
        self.assertEqual(f["M'"], f["M"])

    def test_table_cells(self):
        t = self.g.lookup
        self.assertEqual(str(t("Stmt", "while")), "Stmt -> WhileStmt")
        self.assertEqual(str(t("Stmt", "{")), "Stmt -> Block")
        self.assertTrue(t("M'", ";").is_epsilon)
        self.assertIsNone(t("M'", "color"))
        self.assertIsNone(t("T'", "relop"))
        self.assertIsNone(t("Block", "forward"))

    def test_no_other_cell_is_ambiguous(self):
        # every nonterminal row is deterministic apart from the one conflict
        seen = set()
        for p in self.g.productions:
            first = self.g.first_of_sequence(p.rhs)
            cells = set(first - {"eps"})
            if "eps" in first:
                cells |= self.g.follow[p.lhs]
            for t in cells:
                key = (p.lhs, t)
                if key in seen:
                    self.assertEqual(key, ("ElsePart", "else"))
                seen.add(key)

    def test_text_rendering(self):
        text = grammar.format_all(self.g)
        self.assertIn("59 productions", text)
        self.assertIn("M[ElsePart, else]", text)


from pixelpen import parser  # noqa: E402


def parse_src(source, mode="phrase"):
    lex = lexer.tokenize(source)
    return lex, parser.parse(lex, mode)


def syntax_errors(source, mode="phrase"):
    return parse_src(source, mode)[1].errors


def leaves(node):
    out = []
    todo = [node]
    while todo:
        n = todo.pop()
        if n.token is not None:
            out.append(n)
        todo.extend(reversed(n.children))
    return out


class ParserTests(unittest.TestCase):
    def test_case_study_parses_cleanly(self):
        lex, res = parse_src(CASE_STUDY)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.trace[-1].action, "accept")
        self.assertEqual(len(leaves(res.tree)), 57)

    def test_trace_rows_have_stack_input_action(self):
        _, res = parse_src("turn 1;")
        first = res.trace[0]
        self.assertEqual(first.stack, "$ Program")
        self.assertTrue(first.input.startswith("turn 1 ;"))
        self.assertIn("Program -> StmtList", first.action)

    def test_dangling_else_binds_to_nearest_if(self):
        src = "if (1 < 2) if (2 < 3) turn 1; else turn 2;"
        _, res = parse_src(src)
        self.assertEqual(res.errors, [])
        outer = res.tree
        while outer.symbol != "IfStmt":
            outer = outer.children[0] if outer.children else None
            # descend through StmtList / Stmt to the first IfStmt
            while outer.symbol in ("StmtList", "Stmt"):
                outer = outer.children[0]
        inner_stmt = outer.children[4]            # the Stmt after ')'
        outer_else = outer.children[5]            # ElsePart of the outer if
        self.assertTrue(outer_else.children[0].symbol == "eps")
        inner_if = inner_stmt.children[0]
        self.assertEqual(inner_if.symbol, "IfStmt")
        self.assertEqual(inner_if.children[5].children[0].symbol, "else")

    def test_missing_semicolon_one_error_on_previous_line(self):
        errs = syntax_errors("int size = 40\ncolor c = #FF5733;\npencolor c;")
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].line, 1)
        self.assertIn("missing ';'", errs[0].message)

    def test_panic_mode_skips_the_next_declaration(self):
        errs = syntax_errors("int size = 40\ncolor c = #FF5733;\npencolor c;",
                             "panic")
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].line, 2)

    def test_missing_close_paren(self):
        errs = syntax_errors("int x = 1;\nif (x > 3 {\n turn 1; }")
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].line, 2)
        self.assertIn("missing ')'", errs[0].message)

    def test_missing_close_brace_at_eof(self):
        errs = syntax_errors("repeat 3 {\n turn 1;\n")
        self.assertEqual(len(errs), 1)
        self.assertIn("'}'", errs[0].message)

    def test_unmatched_close_brace_and_recovery_continues(self):
        lex, res = parse_src("turn 1;\n}\nturn 2;\n")
        self.assertEqual(len(res.errors), 1)
        self.assertIn("unmatched '}'", res.errors[0].message)
        self.assertEqual(res.errors[0].line, 2)
        self.assertEqual(len(leaves(res.tree)), 6 + 0)   # both turns parsed

    def test_else_without_if(self):
        errs = syntax_errors("turn 1;\nelse turn 2;")
        self.assertEqual(len(errs), 1)
        self.assertIn("'else' without", errs[0].message)

    def test_chained_comparison(self):
        errs = syntax_errors("int a = 1;\nif (a < 2 < 3) turn 1;")
        self.assertEqual(len(errs), 1)
        self.assertIn("chained comparison", errs[0].message)

    def test_point_with_three_coordinates(self):
        errs = syntax_errors("point p = (1, 2, 3);\nturn 1;")
        self.assertEqual(len(errs), 1)
        self.assertIn("exactly 2 coordinates, found 3", errs[0].message)

    def test_keyword_as_variable_name(self):
        errs = syntax_errors("int circle = 3;\nturn 1;")
        self.assertEqual(len(errs), 1)
        self.assertIn("'circle' is a keyword", errs[0].message)

    def test_missing_operator_between_numbers(self):
        errs = syntax_errors("turn 60 90;")
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].message,
                         "unexpected number '90': missing operator?")

    def test_braceless_loop_body_error_production(self):
        lex, res = parse_src("repeat 4 forward 10;\nturn 1;")
        self.assertEqual(len(res.errors), 1)
        self.assertIn("must be enclosed in '{' and '}'", res.errors[0].message)
        self.assertTrue(any("error production" in t.action for t in res.trace))
        self.assertEqual(len(res.tree.children[0].children), 2)

    def test_braceless_while_body(self):
        errs = syntax_errors("int x = 1;\nwhile (x < 3) x = x + 1;")
        self.assertEqual(len(errs), 1)

    def test_missing_expression(self):
        errs = syntax_errors("forward ;\nturn 1;")
        self.assertEqual(len(errs), 1)
        self.assertIn("expected an expression", errs[0].message)

    def test_cascade_suppression_reports_one_error_for_a_blob(self):
        errs = syntax_errors("turn ) ) ) ;\nturn 1;")
        self.assertEqual(len(errs), 1)

    def test_two_separate_errors_are_both_reported(self):
        errs = syntax_errors("turn 1\nturn 2\nturn 3;")
        self.assertEqual([e.line for e in errs], [1, 2])

    def test_parenthesised_expression_and_point(self):
        _, res = parse_src("point p = (1, 2);\nint k = (3 + 4) * 2;")
        self.assertEqual(res.errors, [])

    def test_fuzz_parser_always_terminates(self):
        import random
        rng = random.Random(402)
        words = ["int", "color", "point", "forward", "turn", "moveto", "penup",
                 "pendown", "pencolor", "circle", "square", "line", "repeat",
                 "while", "if", "else", "and", "or", "not", "x", "y", "12",
                 "#FF00AA", "<", "==", "+", "-", "*", "/", "%", "=", ",", ";",
                 "(", ")", "{", "}"]
        for mode in ("phrase", "panic"):
            for _ in range(400):
                src = " ".join(rng.choice(words)
                               for _ in range(rng.randint(1, 30)))
                lex = lexer.tokenize(src)
                res = parser.parse(lex, mode)
                self.assertEqual(res.trace[-1].action, "accept")


from pixelpen import astbuild, semantic  # noqa: E402


def build(source):
    lex, res = parse_src(source)
    assert not res.errors, res.errors
    return astbuild.build_ast(res.tree)


def check(source):
    return semantic.analyze(build(source))


def messages(source):
    return [d.message for d in check(source).diagnostics]


def init_expr(source):
    """The initializer AST of the first declaration in source."""
    return build(source).stmts[0].init


class AstTests(unittest.TestCase):
    def test_minus_is_left_associative(self):
        e = init_expr("int a = 10 - 4 - 3;")
        self.assertEqual((e.op, e.right.value), ("-", 3))
        self.assertEqual((e.left.op, e.left.left.value, e.left.right.value),
                         ("-", 10, 4))

    def test_division_is_left_associative(self):
        e = init_expr("int a = 100 / 5 / 2;")
        self.assertEqual(e.op, "/")
        self.assertEqual(e.left.op, "/")
        self.assertEqual(e.right.value, 2)

    def test_mixed_additive_chain(self):
        e = init_expr("int a = 1 - 2 + 3;")
        self.assertEqual(e.op, "+")
        self.assertEqual(e.left.op, "-")

    def test_precedence(self):
        e = init_expr("int a = 1 + 2 * 3;")
        self.assertEqual(e.op, "+")
        self.assertEqual(e.right.op, "*")

    def test_unary_minus_and_parentheses(self):
        e = init_expr("int a = -(1 + 2) * 3;")
        self.assertEqual(e.op, "*")
        self.assertEqual(e.left.op, "-")
        self.assertEqual(e.left.operand.op, "+")

    def test_point_versus_parenthesised_int(self):
        self.assertIsInstance(init_expr("point p = (1, 2);"), astbuild.Point)
        self.assertIsInstance(init_expr("int k = (3);"), astbuild.Num)

    def test_logic_precedence_not_and_or(self):
        stmt = build("int a = 1; if (not a < 2 and a > 0 or a == 5) turn 1;"
                     ).stmts[1]
        cond = stmt.cond
        self.assertEqual(cond.op, "or")
        self.assertEqual(cond.left.op, "and")
        self.assertEqual(cond.left.left.op, "not")

    def test_statement_shapes(self):
        prog = build("int n = 1; repeat n { turn 1; } while (n < 3) { n = n + 1; }"
                     " if (n > 1) turn 1; else turn 2; { penup; }")
        names = [type(s).__name__ for s in prog.stmts]
        self.assertEqual(names, ["Decl", "Repeat", "While", "If", "Block"])
        self.assertIsNotNone(prog.stmts[3].otherwise)

    def test_binary_nodes_use_operator_position(self):
        e = init_expr("int a = 1 +  2;")
        self.assertEqual((e.line, e.col), (1, 11))


class SemanticTests(unittest.TestCase):
    def test_case_study_is_clean(self):
        res = check(CASE_STUDY)
        self.assertEqual(res.diagnostics, [])
        self.assertEqual(list(res.symbols), ["size", "petal"])
        self.assertEqual(res.symbols["size"].type, "int")

    def test_arithmetic_needs_int(self):
        m = messages("color c = #FF0000; int a = c + 1;")
        self.assertEqual(len(m), 1)
        self.assertIn("needs int operands, found color and int", m[0])

    def test_ordering_needs_ints(self):
        m = messages("color a = #000000; color b = #FFFFFF; if (a < b) turn 1;")
        self.assertEqual(len(m), 1)
        self.assertIn("'<' needs int operands", m[0])

    def test_equality_ints_or_colors(self):
        ok = "color a = #000000; color b = #FFFFFF; int n = 1; " \
             "if (a == b) turn 1; if (n != 2) turn 2;"
        self.assertEqual(messages(ok), [])
        m = messages("int n = 1; color c = #000000; if (n == c) turn 1;")
        self.assertEqual(len(m), 1)
        self.assertIn("two ints or two colors", m[0])
        m = messages("point p = (1, 2); point q = (1, 2); if (p == q) turn 1;")
        self.assertEqual(len(m), 1)

    def test_logic_needs_bool(self):
        m = messages("int n = 1; if (n and n > 0) turn 1;")
        self.assertEqual(len(m), 1)
        self.assertIn("'and' needs bool operands, found int and bool", m[0])
        m = messages("int n = 1; if (not n) turn 1;")
        self.assertTrue(any("'not' needs a bool operand" in x for x in m))

    def test_conditions_must_be_bool(self):
        m = messages("int n = 1; while (n) { turn 1; }")
        self.assertEqual(len(m), 1)
        self.assertIn("condition of 'while' must be a comparison", m[0])
        m = messages("int n = 1; if (n + 1) turn 1;")
        self.assertIn("condition of 'if'", m[0])

    def test_command_argument_types(self):
        m = messages("color c = #FF0000; forward c; turn c; "
                     "moveto 5; pencolor 7; repeat c { penup; }")
        self.assertEqual(len(m), 5)

    def test_shape_argument_types(self):
        src = ("point p = (0, 0); int r = 5;"
               "circle p, r; square p, r; line p, p;"
               "circle r, p; square 3, #FF0000; line p, 4;")
        m = messages(src)
        self.assertEqual(len(m), 5)       # circle(2) square(2) line(1)

    def test_point_coordinates_must_be_int(self):
        m = messages("point p = (#FF0000, 1);")
        self.assertEqual(len(m), 1)
        self.assertIn("coordinates must be int", m[0])

    def test_declaration_type_mismatch(self):
        m = messages("color c = 5; int n = #FF0000; point p = 3;")
        self.assertEqual(len(m), 3)
        self.assertIn("cannot initialize color variable 'c'", m[0])

    def test_assignment_type_mismatch(self):
        m = messages("int n = 1; n = #FF0000;")
        self.assertEqual(m, ["cannot assign color to 'n' of type int"])

    def test_redeclaration(self):
        m = messages("int a = 1;\nint a = 2;")
        self.assertEqual(len(m), 1)
        self.assertIn("'a' is already declared (first declared on line 1)", m[0])

    def test_undeclared_reported_once(self):
        m = messages("forward ghost; turn ghost + 1; ghost = 4;")
        self.assertEqual(m, ["'ghost' is not declared"])

    def test_self_reference_in_initializer(self):
        m = messages("int x = x + 1;")
        self.assertEqual(m, ["'x' is not declared"])

    def test_division_by_constant_zero(self):
        m = messages("int a = 5 / 0; int b = 5 % (3 - 3); int c = 8 / 2;")
        self.assertEqual(len(m), 2)
        self.assertIn("division by constant 0", m[0])
        self.assertIn("modulo by constant 0", m[1])

    def test_division_by_variable_zero_is_not_static(self):
        self.assertEqual(messages("int d = 0; int a = 5 / d;"), [])

    def test_repeat_zero_is_a_warning(self):
        res = check("repeat 0 { turn 1; }")
        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.warnings), 1)
        self.assertIn("repeat 0", res.warnings[0].message)

    def test_misleading_panic_mode_gives_false_undeclared(self):
        src = "int size = 40\ncolor c = #FF5733;\npencolor c;"
        lex, res = parse_src(src, "panic")
        sem = semantic.analyze(astbuild.build_ast(res.tree))
        self.assertEqual([d.message for d in sem.diagnostics],
                         ["'c' is not declared"])

    def test_symbol_use_counts(self):
        res = check("int a = 1; int b = a + a; turn b;")
        self.assertEqual(res.symbols["a"].uses, 2)
        self.assertEqual(res.symbols["b"].uses, 1)


import math  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

from pixelpen import icg, runtime  # noqa: E402


def gen(source):
    prog = build(source)
    sem = semantic.analyze(prog)
    assert not sem.errors, sem.diagnostics
    return icg.generate(prog, list(sem.symbols))


def listing(source):
    return [q.text() for q in gen(source).quads]


def execute(source, **kwargs):
    res = gen(source)
    return runtime.run(res.quads, res.temps, **kwargs)


class IcgTests(unittest.TestCase):
    def test_case_study_listing(self):
        res = gen(CASE_STUDY)
        self.assertEqual(len(res.quads), 28)
        self.assertEqual(res.labels, ["L1", "L2", "L3", "L4", "L5", "L6"])
        self.assertEqual(res.temps, ["t1", "t2", "t3", "t4", "t5", "t6"])
        self.assertEqual(res.quads[6].text(), "L1: if t2 >= t1 goto L6")
        self.assertEqual(res.quads[27].text(), "L6: halt")

    def test_case_study_full_text(self):
        lines = listing(CASE_STUDY)
        self.assertEqual(lines[0:6], [
            "size = 20", "petal = #FF5733", "param petal",
            "call pencolor, 1", "t1 = 6", "t2 = 0"])
        self.assertEqual(lines[7:16], [
            "if size > 30 goto L2", "goto L4", "L2: if size < 100 goto L3",
            "goto L4", "L3: t3 = mkpoint 0, 0", "param t3", "param size",
            "call square, 2", "goto L5"])
        self.assertEqual(lines[16:], [
            "L4: t4 = mkpoint 0, 0", "t5 = size / 2", "param t4", "param t5",
            "call circle, 2", "L5: param 60", "call turn, 1",
            "t6 = size + 20", "size = t6", "t2 = t2 + 1", "goto L1",
            "L6: halt"])

    def test_while_with_or_uses_jumping_code(self):
        lines = listing("int x = 400; int y = 5;\n"
                        "while (x < 300 or y > 0) { x = x - 1; }")
        i = lines.index("L1: if x < 300 goto L3")
        self.assertEqual(lines[i:i + 4], [
            "L1: if x < 300 goto L3", "goto L2", "L2: if y > 0 goto L3",
            "goto L4"])
        self.assertEqual(lines[-1], "L4: halt")
        self.assertIn("goto L1", lines)

    def test_expression_temps_left_to_right(self):
        lines = listing("int size = 3; int x = 4;\n"
                        "size = size * 2 + (10 - x) % 3;")
        self.assertEqual(lines[2:7], [
            "t1 = size * 2", "t2 = 10 - x", "t3 = t2 % 3", "t4 = t1 + t3",
            "size = t4"])

    def test_unary_minus_and_point(self):
        lines = listing("int a = 5; point p = (-a, 2);")
        self.assertEqual(lines[1:4], ["t1 = minus a", "t2 = mkpoint t1, 2",
                                      "p = t2"])

    def test_short_circuit_and_not(self):
        lines = listing("int a = 1; if (not (a < 2 and a > 0)) turn 1;")
        # 'not' swaps the targets of the whole condition and 'and' short
        # circuits: a false (a < 2) jumps straight to the body (L2)
        self.assertEqual(lines[1:6], [
            "if a < 2 goto L1", "goto L2", "L1: if a > 0 goto L3",
            "goto L2", "L2: param 1"])
        self.assertEqual(lines[-1], "L3: halt")

    def test_no_labels_when_no_jumps(self):
        res = gen("int a = 1; turn a; penup;")
        self.assertEqual(res.labels, [])
        self.assertEqual([q.text() for q in res.quads][-3:],
                         ["call turn, 1", "call penup, 0", "halt"])

    def test_every_label_is_referenced_and_numbering_is_sequential(self):
        res = gen("int a = 1;\nif (a < 2) { if (a < 3) turn 1; }\n"
                  "while (a < 9) { if (a == 5) { a = a + 2; } else turn 1; "
                  "a = a + 1; }")
        targets = {q.result for q in res.quads
                   if q.op == "goto" or q.op.startswith("if")}
        self.assertEqual(targets, set(res.labels))
        self.assertEqual(res.labels,
                         ["L%d" % (i + 1) for i in range(len(res.labels))])

    def test_repeat_snapshots_a_variable_count(self):
        lines = listing("int n = 3; repeat n { n = n + 1; }")
        self.assertEqual(lines[1:3], ["t1 = n", "t2 = 0"])

    def test_repeat_complex_count_reuses_its_temp(self):
        lines = listing("int n = 3; repeat n * 2 { turn 1; }")
        self.assertEqual(lines[1:3], ["t1 = n * 2", "t2 = 0"])

    def test_temps_never_clash_with_user_variables(self):
        res = gen("int t1 = 5; int a = t1 + 1 * 2;")
        self.assertNotIn("t1", res.temps)
        out = runtime.run(res.quads, res.temps)
        self.assertEqual(out.variables["t1"], 5)
        self.assertEqual(out.variables["a"], 7)


class RuntimeTests(unittest.TestCase):
    def test_case_study_drawing(self):
        out = execute(CASE_STUDY)
        self.assertTrue(out.ok)
        drawn = [(d.kind, d.data[2]) for d in out.draws]
        self.assertEqual(drawn, [("circle", 10), ("square", 40),
                                 ("square", 60), ("square", 80),
                                 ("circle", 50), ("circle", 60)])
        self.assertEqual(out.variables["size"], 140)
        self.assertTrue(all(d.color == "#FF5733" for d in out.draws))

    def test_hexagon_closes(self):
        out = execute("repeat 6 { forward 50; turn 60; }")
        self.assertEqual(len(out.draws), 6)
        self.assertAlmostEqual(out.pen["x"], 0.0, places=6)
        self.assertAlmostEqual(out.pen["y"], 0.0, places=6)

    def test_initial_pen_and_direction(self):
        out = execute("forward 10;")
        self.assertEqual(out.draws[0].color, "#000000")
        self.assertAlmostEqual(out.pen["y"], 10.0)
        self.assertAlmostEqual(out.pen["x"], 0.0)

    def test_turn_is_counterclockwise(self):
        out = execute("turn 90; forward 10;")
        self.assertAlmostEqual(out.pen["x"], -10.0)
        self.assertAlmostEqual(out.pen["y"], 0.0)

    def test_penup_and_moveto_do_not_draw(self):
        out = execute("penup; forward 10; pendown; moveto (5, 5);"
                      " forward 1;")
        self.assertEqual(len(out.draws), 1)
        self.assertEqual(out.draws[0].data[:2], (5.0, 5.0))

    def test_shapes_are_centred_and_line_uses_points(self):
        out = execute("circle (3, 4), 5; square (1, 2), 6;"
                      " line (0, 0), (7, 8);")
        self.assertEqual(out.draws[0].data, (3, 4, 5))
        self.assertEqual(out.draws[1].data, (1, 2, 6))
        self.assertEqual(out.draws[2].data, (0, 0, 7, 8))

    def test_integer_division_truncates_toward_zero(self):
        out = execute("int a = 0 - 7; int q = a / 2; int r = a % 2;"
                      " int s = 7 % (0 - 2); int t = 7 / (0 - 2);")
        v = out.variables
        self.assertEqual((v["q"], v["r"], v["s"], v["t"]), (-3, -1, 1, -3))

    def test_division_by_zero(self):
        out = execute("int d = 0;\nint a = 5 / d;")
        self.assertFalse(out.ok)
        self.assertEqual(out.error.phase, "runtime")
        self.assertEqual(out.error.line, 2)
        self.assertIn("division by zero", out.error.message)

    def test_modulo_by_zero(self):
        out = execute("int d = 0; int a = 5 % d;")
        self.assertIn("division by zero", out.error.message)

    def test_negative_size(self):
        out = execute("int r = 0 - 5;\ncircle (0, 0), r;")
        self.assertIn("negative size", out.error.message)
        out = execute("square (0, 0), 0 - 1;")
        self.assertIn("negative size", out.error.message)

    def test_zero_size_is_fine(self):
        self.assertTrue(execute("circle (0, 0), 0;").ok)

    def test_step_limit_stops_infinite_loop(self):
        out = execute("int x = 1; while (x > 0) { x = x + 1; }")
        self.assertFalse(out.ok)
        self.assertIn("200000", out.error.message)
        self.assertGreater(out.steps, 200000)

    def test_variable_without_value(self):
        out = execute("int a = 1; if (a > 5) { int b = 2; } turn b;")
        self.assertIn("'b' has no value yet", out.error.message)

    def test_color_comparison_and_while(self):
        out = execute("color c = #00FF00; int n = 0;"
                      " while (n < 3) { if (c == #00FF00) { n = n + 1; } }")
        self.assertEqual(out.variables["n"], 3)

    def test_repeat_count_is_evaluated_once(self):
        out = execute("int n = 3; int k = 0; repeat n { n = n + 1; k = k + 1; }")
        self.assertEqual(out.variables["k"], 3)

    def test_repeat_zero_and_negative_run_no_iterations(self):
        out = execute("int k = 0; repeat 0 { k = k + 1; }"
                      " repeat 0 - 4 { k = k + 1; }")
        self.assertEqual(out.variables["k"], 0)

    def test_log_is_recorded(self):
        out = execute("forward 10; turn 90; pencolor #FF0000;")
        self.assertTrue(any(l.startswith("forward 10") for l in out.log))
        self.assertEqual(len(out.log), 3)

    def test_svg_export_is_valid_xml(self):
        out = execute(CASE_STUDY + "line (0, 0), (50, 50); forward 20;")
        svg = runtime.to_svg(out.draws)
        root = ET.fromstring(svg)
        tags = [el.tag.split("}")[1] for el in root]
        self.assertEqual(tags.count("circle"), 3)
        self.assertEqual(tags.count("rect"), 1 + 3)    # background + 3 squares
        self.assertEqual(tags.count("line"), 2)
        self.assertIn("#FF5733", svg)

    def test_svg_of_empty_drawing(self):
        root = ET.fromstring(runtime.to_svg([]))
        self.assertTrue(root.tag.endswith("svg"))

    def test_heading_after_many_turns(self):
        out = execute("turn 450;")
        self.assertAlmostEqual(out.pen["heading"], (90 + 450) % 360)
        self.assertTrue(math.isfinite(out.pen["x"]))


import io  # noqa: E402
import tempfile  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402

import pixelpen_cli  # noqa: E402
from pixelpen import compiler  # noqa: E402

MISLEADING = "int size = 40\ncolor c = #FF5733;\npencolor c;"


class CompilerTests(unittest.TestCase):
    def test_case_study_end_to_end(self):
        res = compiler.compile_source(CASE_STUDY)
        self.assertTrue(res.ok)
        self.assertEqual(res.diagnostics, [])
        self.assertEqual(len(res.lex.tokens), 57)
        self.assertEqual(len(res.icg.quads), 28)
        self.assertEqual(res.run.variables["size"], 140)

    def test_phrase_mode_reports_one_error_on_line_1(self):
        res = compiler.compile_source(MISLEADING)
        self.assertEqual(len(res.diagnostics), 1)
        d = res.diagnostics[0]
        self.assertEqual((d.phase, d.line), ("syntax", 1))
        self.assertIsNone(res.semantic)         # semantic skipped on errors
        self.assertIsNone(res.icg)

    def test_panic_mode_gives_a_false_undeclared_error(self):
        res = compiler.compile_source(MISLEADING, mode="panic")
        msgs = [(d.phase, d.message) for d in res.diagnostics]
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0][0], "syntax")
        self.assertEqual(msgs[1], ("semantic", "'c' is not declared"))
        self.assertIsNone(res.icg)              # no code when errors exist

    def test_lexical_error_blocks_semantic_phase(self):
        res = compiler.compile_source("int a = 5;\ncolor c = #FF57;\nturn a;")
        phases = {d.phase for d in res.diagnostics}
        self.assertIn("lexical", phases)
        self.assertNotIn("semantic", phases)
        self.assertIsNone(res.semantic)

    def test_hex_error_is_followed_by_parsing(self):
        res = compiler.compile_source("color c = #FF57;\nturn 1;")
        self.assertEqual([d.phase for d in res.diagnostics], ["lexical"])

    def test_warnings_do_not_stop_execution(self):
        res = compiler.compile_source("repeat 0 { turn 1; } forward 5;")
        self.assertTrue(res.ok)
        self.assertEqual(len(res.warnings), 1)
        self.assertIsNotNone(res.run)

    def test_runtime_error_becomes_a_diagnostic(self):
        res = compiler.compile_source("int d = 0;\nforward 5 / d;")
        self.assertEqual(res.diagnostics[-1].phase, "runtime")
        self.assertEqual(res.diagnostics[-1].line, 2)
        self.assertFalse(res.ok)

    def test_semantic_errors_are_collected(self):
        res = compiler.compile_source("int a = #FF0000;\nforward ghost;")
        self.assertEqual([d.phase for d in res.diagnostics],
                         ["semantic", "semantic"])
        self.assertIsNone(res.icg)

    def test_while_or_through_the_driver(self):
        res = compiler.compile_source(
            "int x = 400; int y = 3; while (x < 300 or y > 0) { y = y - 1; }")
        texts = [q.text() for q in res.icg.quads]
        i = texts.index("L1: if x < 300 goto L3")
        self.assertEqual(texts[i + 1:i + 4], [
            "goto L2", "L2: if y > 0 goto L3", "goto L4"])
        self.assertTrue(res.ok)
        self.assertEqual(res.run.variables["y"], 0)

    def test_expression_example_through_the_driver(self):
        res = compiler.compile_source(
            "int size = 3; int x = 4; size = size * 2 + (10 - x) % 3;")
        texts = [q.text() for q in res.icg.quads]
        self.assertEqual(texts[2:6], ["t1 = size * 2", "t2 = 10 - x",
                                      "t3 = t2 % 3", "t4 = t1 + t3"])
        self.assertEqual(res.run.variables["size"], 6)


class CliTests(unittest.TestCase):
    def run_cli(self, source, *flags):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.pp")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(source)
            out = io.StringIO()
            with redirect_stdout(out):
                code = pixelpen_cli.main([path] + list(flags))
        return code, out.getvalue()

    def test_clean_program(self):
        code, out = self.run_cli(CASE_STUDY)
        self.assertEqual(code, 0)
        self.assertIn("No errors or warnings.", out)
        self.assertIn("size = 140", out)

    def test_all_listing_flags(self):
        code, out = self.run_cli(CASE_STUDY, "--tokens", "--tree", "--trace",
                                 "--quads")
        self.assertEqual(code, 0)
        for heading in ("TOKENS (57)", "PARSE TREE", "LL(1) TRACE",
                        "THREE-ADDRESS CODE", "QUADRUPLES",
                        "L6: halt"):
            self.assertIn(heading, out)

    def test_error_exit_code_and_panic_flag(self):
        code, out = self.run_cli(MISLEADING)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("error"), 1)
        code, out = self.run_cli(MISLEADING, "--panic")
        self.assertIn("'c' is not declared", out)

    def test_svg_flag_writes_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg = os.path.join(tmp, "out.svg")
            code, out = self.run_cli("circle (0, 0), 10;", "--svg", svg)
            self.assertEqual(code, 0)
            with open(svg, encoding="utf-8") as handle:
                self.assertIn("<circle", handle.read())

    def test_grammar_flag_needs_no_file(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = pixelpen_cli.main(["--grammar"])
        self.assertEqual(code, 0)
        self.assertIn("27 nonterminals", out.getvalue())


EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "examples")


def example(name):
    with open(os.path.join(EXAMPLES, name), encoding="utf-8") as handle:
        return handle.read()


class ExampleTests(unittest.TestCase):
    def test_there_are_twelve_examples(self):
        files = [f for f in os.listdir(EXAMPLES) if f.endswith(".pp")]
        self.assertEqual(len(files), 12)

    def test_case_study_file_matches_the_report(self):
        res = compiler.compile_source(example("01_case_study.pp"))
        self.assertEqual(len(res.lex.tokens), 57)
        self.assertEqual(res.diagnostics, [])
        self.assertEqual(len(res.icg.quads), 28)

    def test_clean_examples_run_without_diagnostics(self):
        for name in ("01_case_study.pp", "02_hexagon.pp", "03_while_spiral.pp",
                     "04_nested_stars.pp", "05_points_lines.pp"):
            res = compiler.compile_source(example(name))
            self.assertEqual(res.diagnostics, [], name)
            self.assertGreater(len(res.run.draws), 0, name)

    def test_hexagon_example_closes(self):
        res = compiler.compile_source(example("02_hexagon.pp"))
        self.assertAlmostEqual(res.run.pen["x"], -40.0, places=6)
        self.assertAlmostEqual(res.run.pen["y"], -70.0, places=6)

    def test_while_spiral_uses_or(self):
        res = compiler.compile_source(example("03_while_spiral.pp"))
        self.assertEqual(res.run.variables["side"], 150)
        self.assertEqual(res.run.variables["turns"], 29)

    def test_nested_stars_else_binds_to_inner_if(self):
        res = compiler.compile_source(example("04_nested_stars.pp"))
        colors = [d.color for d in res.run.draws]
        # level 0: black, level 1: inner else -> violet, level 2: orange
        self.assertEqual(colors[:5], ["#000000"] * 5)
        self.assertEqual(colors[5:10], ["#6A1B9A"] * 5)
        self.assertEqual(colors[10:], ["#EF6C00"] * 5)

    def test_boundary_cases(self):
        res = compiler.compile_source(example("06_boundary_cases.pp"))
        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.warnings), 1)
        v = res.run.variables
        self.assertEqual((v["q"], v["r"], v["mix"]), (-3, -1, 13))

    def test_lexical_error_example(self):
        res = compiler.compile_source(example("07_lexical_errors.pp"))
        self.assertEqual([d.phase for d in res.diagnostics], ["lexical"] * 6)

    def test_ten_syntax_errors_each_reported_once(self):
        res = compiler.compile_source(example("08_syntax_errors.pp"))
        self.assertEqual(len(res.diagnostics), 10)
        self.assertTrue(all(d.phase == "syntax" for d in res.diagnostics))
        lines = [d.line for d in res.diagnostics]
        self.assertEqual(lines, sorted(set(lines)))

    def test_semantic_error_example(self):
        res = compiler.compile_source(example("09_semantic_errors.pp"))
        self.assertEqual(len(res.errors), 16)
        self.assertEqual(len(res.warnings), 1)
        self.assertEqual(sum("ghost" in d.message for d in res.errors), 1)

    def test_misleading_recovery_example(self):
        src = example("10_misleading_recovery.pp")
        phrase = compiler.compile_source(src, "phrase")
        self.assertEqual([(d.phase, d.line) for d in phrase.diagnostics],
                         [("syntax", 1)])
        panic = compiler.compile_source(src, "panic")
        self.assertEqual(panic.diagnostics[-1].message,
                         "'c' is not declared")

    def test_runtime_error_example(self):
        res = compiler.compile_source(example("11_runtime_errors.pp"))
        self.assertEqual(res.diagnostics[-1].phase, "runtime")
        self.assertIn("division by zero", res.diagnostics[-1].message)
        self.assertEqual(len(res.run.draws), 1)         # drawing kept

    def test_infinite_loop_example(self):
        res = compiler.compile_source(example("12_infinite_loop.pp"))
        self.assertIn("step limit", res.diagnostics[-1].message)


class GuiSmokeTests(unittest.TestCase):
    """Builds the real window once; skipped when there is no display."""

    def test_window_compiles_every_example(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        try:
            import app
            window = app.App(root)
            root.update()
            for name in sorted(window.example_paths):
                for mode in app.RECOVERY_MODES:
                    window.example_box.set(name)
                    window.recovery_box.set(mode)
                    window.load_example()
                    root.update()
                    self.assertIsNotNone(window.result)
            window.example_box.set("08_syntax_errors")
            window.recovery_box.set("Phrase-level (default)")
            window.load_example()
            root.update()
            rows = window.diag_table.get_children()
            self.assertEqual(len(rows), 10)
            window.diag_table.selection_set(rows[0])
            root.update()
            self.assertEqual(window.text.index("insert").split(".")[0], "2")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
