"""PixelPen workbench: a Tkinter GUI for the whole compiler pipeline.

Run with:  python app.py

Left:   code editor (line numbers, syntax highlighting)
Right:  one tab per phase (drawing, tokens, parse tree, LL(1) trace, symbols,
        code, grammar)
Bottom: the diagnostics table; click a row to jump to that line.
F5 compiles and runs the program.
"""

import math
import os
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from pixelpen import grammar, icg, lexer, parser, runtime
from pixelpen.compiler import compile_source

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.join(HERE, "examples")

# light, minimal palette
BG = "#F7F7F5"
PANEL = "#FFFFFF"
FG = "#1F2328"
MUTED = "#6B7280"
BORDER = "#D9DCE0"
ACCENT = "#2563EB"
ACCENT_DARK = "#1D4ED8"
GUTTER = "#F1F2F4"
ERR_BG = "#FDE7E7"
WARN_BG = "#FFF4D6"
ERR_FG = "#B42318"
WARN_FG = "#9A6700"

RECOVERY_MODES = {"Phrase-level (default)": "phrase",
                  "Panic mode only": "panic"}

TYPE_WORDS = ("int", "color", "point")


def pick_mono_font(root):
    families = set(tkfont.families(root))
    for name in ("Consolas", "Cascadia Mono", "DejaVu Sans Mono",
                 "Menlo", "Courier New"):
        if name in families:
            return name
    return "TkFixedFont"


class LineNumbers(tk.Canvas):
    """A gutter that shows the line numbers of a Text widget."""

    def __init__(self, master, text, font, **kwargs):
        tk.Canvas.__init__(self, master, width=52, highlightthickness=0,
                           bg=GUTTER, **kwargs)
        self.text = text
        self.font = font

    def redraw(self):
        self.delete("all")
        last = int(self.text.index("end-1c").split(".")[0])
        index = self.text.index("@0,0")
        width = int(self["width"])
        while True:
            info = self.text.dlineinfo(index)
            if info is None:
                break
            number = int(index.split(".")[0])
            self.create_text(width - 8, info[1], anchor="ne", fill=MUTED,
                             font=self.font, text=str(number))
            if number >= last:
                break
            index = self.text.index("%d.0" % (number + 1))


class App:
    def __init__(self, root):
        self.root = root
        root.title("PixelPen workbench")
        root.configure(bg=BG)
        root.geometry("1380x860")
        root.minsize(1000, 640)
        self.scale = max(root.winfo_fpixels("1i") / 96.0, 1.0)
        self.mono = pick_mono_font(root)
        self.code_font = tkfont.Font(family=self.mono, size=11)
        self.small_mono = tkfont.Font(family=self.mono, size=10)
        self.ui_font = tkfont.Font(family="Segoe UI", size=10)
        self.result = None
        self.last_draws = None
        self.last_pen = None
        self.highlight_job = None
        self.example_paths = self._find_examples()

        self._style()
        self._build_toolbar()
        self._build_panes()
        self._build_status()
        self._fill_grammar_tab()

        root.bind_all("<F5>", lambda e: self.compile())
        root.bind_all("<Control-Return>", lambda e: self.compile())
        if self.example_paths:
            first = sorted(self.example_paths)[0]
            self.example_box.set(first)
            self.load_example()
        else:
            self.compile()

    # -- setup -----------------------------------------------------------------

    def px(self, value):
        return int(value * self.scale)

    def _find_examples(self):
        paths = {}
        if os.path.isdir(EXAMPLES_DIR):
            for name in sorted(os.listdir(EXAMPLES_DIR)):
                if name.endswith(".pp"):
                    paths[name[:-3]] = os.path.join(EXAMPLES_DIR, name)
        return paths

    def _style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=FG,
                        font=self.ui_font)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=MUTED)
        style.configure("Status.TLabel", background=BG, foreground=MUTED)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(self.px(14), self.px(6)),
                        background=BG, foreground=MUTED, borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", PANEL)],
                  foreground=[("selected", FG)])
        style.configure("TButton", padding=(self.px(10), self.px(5)),
                        background=PANEL, bordercolor=BORDER,
                        lightcolor=PANEL, darkcolor=PANEL)
        style.map("TButton", background=[("active", GUTTER)])
        style.configure("Accent.TButton", background=ACCENT,
                        foreground="#FFFFFF", bordercolor=ACCENT,
                        lightcolor=ACCENT, darkcolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("active", ACCENT_DARK)],
                  foreground=[("active", "#FFFFFF")])
        style.configure("TCombobox", fieldbackground=PANEL,
                        background=PANEL, arrowcolor=MUTED)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=self.px(22),
                        bordercolor=BORDER, borderwidth=0)
        style.configure("Treeview.Heading", background=GUTTER,
                        foreground=FG, relief="flat",
                        padding=(self.px(6), self.px(4)))
        style.map("Treeview", background=[("selected", "#DBEAFE")],
                  foreground=[("selected", FG)])
        style.configure("TPanedwindow", background=BG)
        style.configure("Sash", sashthickness=self.px(6), background=BG)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(side="top", fill="x", padx=self.px(12), pady=(self.px(10), 0))
        ttk.Label(bar, text="Example").pack(side="left")
        self.example_box = ttk.Combobox(
            bar, state="readonly", width=26,
            values=sorted(self.example_paths))
        self.example_box.pack(side="left", padx=(self.px(6), self.px(16)))
        self.example_box.bind("<<ComboboxSelected>>",
                              lambda e: self.load_example())
        ttk.Label(bar, text="Recovery").pack(side="left")
        self.recovery_box = ttk.Combobox(
            bar, state="readonly", width=22,
            values=list(RECOVERY_MODES))
        self.recovery_box.set("Phrase-level (default)")
        self.recovery_box.pack(side="left", padx=(self.px(6), self.px(16)))
        self.recovery_box.bind("<<ComboboxSelected>>",
                               lambda e: self.compile())
        ttk.Button(bar, text="Open file...",
                   command=self.open_file).pack(side="left")
        ttk.Button(bar, text="Save SVG...",
                   command=self.save_svg).pack(side="left", padx=self.px(6))
        ttk.Button(bar, text="Compile and run (F5)", style="Accent.TButton",
                   command=self.compile).pack(side="right")

    def _build_panes(self):
        outer = ttk.PanedWindow(self.root, orient="vertical")
        outer.pack(fill="both", expand=True, padx=self.px(12),
                   pady=self.px(10))
        upper = ttk.PanedWindow(outer, orient="horizontal")
        outer.add(upper, weight=4)
        self._build_editor(upper)
        self._build_tabs(upper)
        self._build_diagnostics(outer)

    def _build_editor(self, parent):
        frame = tk.Frame(parent, bg=BORDER, bd=0)
        inner = tk.Frame(frame, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.text = tk.Text(inner, wrap="none", undo=True, font=self.code_font,
                            bg=PANEL, fg=FG, insertbackground=FG, bd=0,
                            highlightthickness=0, padx=self.px(8),
                            pady=self.px(6), tabs=(self.px(32),),
                            selectbackground="#BFDBFE", selectforeground=FG)
        self.numbers = LineNumbers(inner, self.text, self.small_mono)
        vbar = ttk.Scrollbar(inner, orient="vertical", command=self._yview)
        hbar = ttk.Scrollbar(inner, orient="horizontal",
                             command=self.text.xview)
        self.vbar = vbar
        self.text.configure(yscrollcommand=self._on_yscroll,
                            xscrollcommand=hbar.set)
        self.numbers.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        vbar.grid(row=0, column=2, sticky="ns")
        hbar.grid(row=1, column=1, sticky="ew")
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)
        parent.add(frame, weight=2)

        t = self.text
        t.tag_configure("kw", foreground="#7C3AED")
        t.tag_configure("type", foreground="#0F766E")
        t.tag_configure("num", foreground="#B45309")
        t.tag_configure("hex", foreground="#BE185D")
        t.tag_configure("comment", foreground="#9CA3AF",
                        font=tkfont.Font(family=self.mono, size=11,
                                         slant="italic"))
        t.tag_configure("lexerr", underline=True, foreground=ERR_FG)
        t.tag_configure("errline", background=ERR_BG)
        t.tag_configure("warnline", background=WARN_BG)
        t.tag_lower("errline")
        t.tag_lower("warnline")
        t.tag_raise("sel")
        t.bind("<<Modified>>", self._on_modified)
        t.bind("<Tab>", self._on_tab)
        t.bind("<Return>", self._on_return)
        t.bind("<Configure>", lambda e: self.numbers.redraw())
        t.bind("<MouseWheel>", lambda e: self.root.after(1, self.numbers.redraw))

    def _build_tabs(self, parent):
        self.tabs = ttk.Notebook(parent)
        parent.add(self.tabs, weight=3)

        # Drawing: canvas above a runtime log
        draw = ttk.PanedWindow(self.tabs, orient="vertical")
        self.canvas = tk.Canvas(draw, bg="#FFFFFF", highlightthickness=1,
                                highlightbackground=BORDER)
        self.canvas.bind("<Configure>", lambda e: self._draw_canvas())
        draw.add(self.canvas, weight=4)
        self.log_text = self._text_widget(draw, self.small_mono, height=7)
        draw.add(self.log_text.master, weight=1)
        self.tabs.add(draw, text="Drawing")

        self.token_table = self._table(
            ("no", "line", "col", "kind", "lexeme"),
            ("#", "Line", "Col", "Kind", "Lexeme"), (60, 60, 60, 110, 240))
        self.tabs.add(self.token_table.master, text="Tokens")

        tree_frame = ttk.Frame(self.tabs)
        buttons = ttk.Frame(tree_frame)
        buttons.pack(fill="x", pady=(self.px(4), self.px(4)))
        ttk.Button(buttons, text="Expand all",
                   command=lambda: self._set_open(True)).pack(side="left")
        ttk.Button(buttons, text="Collapse all",
                   command=lambda: self._set_open(False)).pack(
            side="left", padx=self.px(6))
        self.tree_view = ttk.Treeview(tree_frame, show="tree")
        self.tree_view.column("#0", width=self.px(1400), stretch=False)
        self._attach_scrollbars(tree_frame, self.tree_view)
        self.tabs.add(tree_frame, text="Parse tree")

        self.trace_table = self._table(
            ("step", "stack", "input", "action"),
            ("Step", "Stack (top at right)", "Input", "Action"),
            (60, 330, 260, 520))
        self.trace_table.tag_configure("error", foreground=ERR_FG,
                                       background=ERR_BG)
        self.trace_table.tag_configure("suppressed", foreground=WARN_FG,
                                       background=WARN_BG)
        self.tabs.add(self.trace_table.master, text="LL(1) trace")

        self.symbol_table = self._table(
            ("name", "type", "line", "uses", "value"),
            ("Name", "Type", "Declared on line", "Uses", "Final value"),
            (160, 120, 140, 80, 220))
        self.tabs.add(self.symbol_table.master, text="Symbols")

        code = ttk.PanedWindow(self.tabs, orient="vertical")
        self.tac_text = self._text_widget(code, self.code_font, height=10)
        code.add(self.tac_text.master, weight=3)
        self.quad_table = self._table(
            ("no", "label", "op", "arg1", "arg2", "result"),
            ("#", "Label", "Op", "Arg 1", "Arg 2", "Result"),
            (50, 70, 90, 140, 140, 120), parent=code)
        code.add(self.quad_table.master, weight=3)
        self.tabs.add(code, text="Code")

        self.grammar_text = self._text_widget(self.tabs, self.small_mono,
                                              wrap="none", hscroll=True)
        self.grammar_text.tag_configure("heading", foreground=ACCENT,
                                        font=tkfont.Font(family=self.mono,
                                                         size=11,
                                                         weight="bold"))
        self.grammar_text.tag_configure("conflict", foreground=ERR_FG,
                                        background=ERR_BG)
        self.tabs.add(self.grammar_text.master, text="Grammar")

    def _build_diagnostics(self, parent):
        frame = ttk.Frame(parent)
        self.diag_table = self._table(
            ("phase", "line", "col", "severity", "message"),
            ("Phase", "Line", "Col", "Severity", "Message"),
            (90, 60, 60, 90, 900), parent=frame, stretch_last=True)
        self.diag_table.tag_configure("error", foreground=ERR_FG)
        self.diag_table.tag_configure("warning", foreground=WARN_FG)
        self.diag_table.master.pack(fill="both", expand=True)
        self.diag_table.bind("<<TreeviewSelect>>", self._on_diag_select)
        parent.add(frame, weight=1)

    def _build_status(self):
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status,
                  style="Status.TLabel").pack(side="bottom", anchor="w",
                                              padx=self.px(14),
                                              pady=(0, self.px(6)))

    # -- widget helpers -------------------------------------------------------------

    def _attach_scrollbars(self, frame, widget, horizontal=True):
        vbar = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
        widget.configure(yscrollcommand=vbar.set)
        if horizontal:
            hbar = ttk.Scrollbar(frame, orient="horizontal",
                                 command=widget.xview)
            widget.configure(xscrollcommand=hbar.set)
        if horizontal:
            hbar.pack(side="bottom", fill="x")
        vbar.pack(side="right", fill="y")
        widget.pack(side="left", fill="both", expand=True)

    def _table(self, columns, headings, widths, parent=None, stretch_last=False):
        frame = ttk.Frame(parent or self.tabs)
        tree = ttk.Treeview(frame, columns=columns, show="headings",
                            selectmode="browse")
        for i, (col, head, width) in enumerate(zip(columns, headings, widths)):
            last = stretch_last and i == len(columns) - 1
            tree.heading(col, text=head, anchor="w")
            tree.column(col, width=self.px(width), anchor="w",
                        stretch=last, minwidth=self.px(40))
        self._attach_scrollbars(frame, tree)
        return tree

    def _text_widget(self, parent, font, height=None, wrap="word",
                     hscroll=False):
        frame = tk.Frame(parent, bg=BORDER)
        text = tk.Text(frame, font=font, bg=PANEL, fg=FG, wrap=wrap, bd=0,
                       highlightthickness=0, padx=self.px(8),
                       pady=self.px(6), state="disabled",
                       selectbackground="#BFDBFE", selectforeground=FG)
        if height:
            text.configure(height=height)
        vbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=vbar.set)
        inner_bottom = None
        if hscroll:
            inner_bottom = ttk.Scrollbar(frame, orient="horizontal",
                                         command=text.xview)
            text.configure(xscrollcommand=inner_bottom.set)
            inner_bottom.pack(side="bottom", fill="x")
        vbar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        return text

    @staticmethod
    def _set_text(widget, content):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    @staticmethod
    def _clear(tree):
        tree.delete(*tree.get_children())

    # -- editor behaviour --------------------------------------------------------------

    def _yview(self, *args):
        self.text.yview(*args)
        self.numbers.redraw()

    def _on_yscroll(self, first, last):
        self.vbar.set(first, last)
        self.numbers.redraw()

    def _on_modified(self, _event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.numbers.redraw()
            self.text.tag_remove("errline", "1.0", "end")
            self.text.tag_remove("warnline", "1.0", "end")
            if self.highlight_job:
                self.root.after_cancel(self.highlight_job)
            self.highlight_job = self.root.after(120, self.highlight)

    def _on_tab(self, _event):
        self.text.insert("insert", "    ")
        return "break"

    def _on_return(self, _event):
        line = self.text.get("insert linestart", "insert")
        indent = line[:len(line) - len(line.lstrip(" \t"))]
        if line.rstrip().endswith("{"):
            indent += "    "
        self.text.insert("insert", "\n" + indent)
        self.text.see("insert")
        return "break"

    def highlight(self):
        """Colour the source using the real lexer (no regular expressions)."""
        self.highlight_job = None
        t = self.text
        for tag in ("kw", "type", "num", "hex", "comment", "lexerr"):
            t.tag_remove(tag, "1.0", "end")
        result = lexer.tokenize(t.get("1.0", "end-1c"))
        for tok in result.tokens:
            start = "%d.%d" % (tok.line, tok.col - 1)
            end = "%d.%d" % (tok.line, tok.col - 1 + len(tok.lexeme))
            if tok.error:
                t.tag_add("lexerr", start, end)
            elif tok.kind in TYPE_WORDS:
                t.tag_add("type", start, end)
            elif tok.kind in lexer.KEYWORD_SET:
                t.tag_add("kw", start, end)
            elif tok.kind == "num":
                t.tag_add("num", start, end)
            elif tok.kind == "hex":
                t.tag_add("hex", start, end)
        for line, col, length in result.comments:
            t.tag_add("comment", "%d.%d" % (line, col - 1),
                      "%d.%d" % (line, col - 1 + length))
        t.tag_raise("sel")

    def set_source(self, source):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", source)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.numbers.redraw()
        self.highlight()

    # -- file actions ---------------------------------------------------------------------

    def load_example(self):
        path = self.example_paths.get(self.example_box.get())
        if not path:
            return
        with open(path, "r", encoding="utf-8") as handle:
            self.set_source(handle.read())
        self.compile()

    def open_file(self):
        path = filedialog.askopenfilename(
            initialdir=EXAMPLES_DIR if os.path.isdir(EXAMPLES_DIR) else HERE,
            filetypes=[("PixelPen", "*.pp"), ("All files", "*.*")])
        if path:
            with open(path, "r", encoding="utf-8") as handle:
                self.set_source(handle.read())
            self.example_box.set("")
            self.compile()

    def save_svg(self):
        if self.result is None or self.result.run is None:
            messagebox.showinfo("Save SVG", "Nothing to save: run a program "
                                            "without errors first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".svg",
                                            filetypes=[("SVG", "*.svg")])
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(runtime.to_svg(self.result.run.draws))
            self.status.set("Saved " + path)

    # -- compiling and showing the results -----------------------------------------------------

    def compile(self):
        source = self.text.get("1.0", "end-1c")
        mode = RECOVERY_MODES.get(self.recovery_box.get(), "phrase")
        self.result = compile_source(source, mode)
        r = self.result
        self._show_tokens(r)
        self._show_tree(r)
        self._show_trace(r)
        self._show_symbols(r)
        self._show_code(r)
        self._show_diagnostics(r)
        self._show_runtime(r)
        self._shade_error_lines(r)
        errors, warnings = len(r.errors), len(r.warnings)
        if errors:
            self.status.set("%d error(s), %d warning(s). Recovery: %s."
                            % (errors, warnings, mode))
        elif r.run is not None:
            self.status.set("OK: %d instruction(s) executed, %d warning(s)."
                            % (r.run.steps, warnings))
        else:
            self.status.set("Compiled.")

    def _show_tokens(self, r):
        self._clear(self.token_table)
        for i, t in enumerate(r.lex.tokens + [r.lex.eof], 1):
            self.token_table.insert("", "end", values=(
                i, t.line, t.col, t.kind,
                (t.lexeme or "(end of input)") + ("   <- error" if t.error
                                                  else "")))

    def _show_tree(self, r):
        view = self.tree_view
        self._clear(view)
        todo = [("", r.parse.tree)]
        while todo:
            parent, node = todo.pop()
            iid = view.insert(parent, "end", text=node.label(), open=True)
            for child in reversed(node.children):
                todo.append((iid, child))

    def _set_open(self, state):
        todo = list(self.tree_view.get_children())
        while todo:
            iid = todo.pop()
            self.tree_view.item(iid, open=state)
            todo.extend(self.tree_view.get_children(iid))

    def _show_trace(self, r):
        self._clear(self.trace_table)
        for step in r.parse.trace:
            tag = ()
            if step.action.startswith("ERROR"):
                tag = ("error",)
            elif step.action.startswith("error suppressed"):
                tag = ("suppressed",)
            self.trace_table.insert("", "end", tags=tag, values=(
                step.step, step.stack, step.input, step.action))

    def _show_symbols(self, r):
        self._clear(self.symbol_table)
        if r.semantic is None:
            self.symbol_table.insert("", "end", values=(
                "(semantic analysis was skipped because of earlier errors)",
                "", "", "", ""))
            return
        values = r.run.variables if r.run else {}
        for sym in r.semantic.symbols.values():
            kind = "err (not declared)" if sym.type == "err" else sym.type
            shown = runtime.show(values[sym.name]) if sym.name in values else ""
            self.symbol_table.insert("", "end", values=(
                sym.name, kind, sym.line, sym.uses, shown))

    def _show_code(self, r):
        self._clear(self.quad_table)
        if r.icg is None:
            self._set_text(self.tac_text,
                           "No code was generated.\nFix the errors listed "
                           "below and compile again.")
            return
        self._set_text(self.tac_text, icg.format_listing(r.icg.quads))
        for i, q in enumerate(r.icg.quads, 1):
            self.quad_table.insert("", "end", values=(
                i, q.label or "", q.op,
                "" if q.arg1 is None else q.arg1,
                "" if q.arg2 is None else q.arg2,
                "" if q.result is None else q.result))

    def _show_diagnostics(self, r):
        self._clear(self.diag_table)
        for d in r.diagnostics:
            self.diag_table.insert("", "end", tags=(d.severity,), values=(
                d.phase, d.line, d.col, d.severity, d.message))

    def _show_runtime(self, r):
        if r.run is None:
            if r.errors:
                note = "Nothing was run because of the errors below."
            else:
                note = "Nothing was run."
            self._set_text(self.log_text, note)
            self.last_draws = []
            self.last_pen = None
        else:
            run = r.run
            lines = ["Executed %d instructions, %d drawing operations."
                     % (run.steps, len(run.draws))]
            lines += run.log
            self._set_text(self.log_text, "\n".join(lines))
            self.last_draws = run.draws
            self.last_pen = run.pen
        self._draw_canvas()
        if r.run is not None:
            self.tabs.select(0)

    def _shade_error_lines(self, r):
        t = self.text
        t.tag_remove("errline", "1.0", "end")
        t.tag_remove("warnline", "1.0", "end")
        last = int(t.index("end-1c").split(".")[0])
        for d in r.diagnostics:
            if 1 <= d.line <= last:
                tag = "errline" if d.severity == "error" else "warnline"
                t.tag_add(tag, "%d.0" % d.line, "%d.0 lineend+1c" % d.line)

    def _on_diag_select(self, _event=None):
        selected = self.diag_table.selection()
        if not selected:
            return
        values = self.diag_table.item(selected[0], "values")
        line, col = int(values[1]), int(values[2])
        self.text.mark_set("insert", "%d.%d" % (line, max(col - 1, 0)))
        self.text.see("insert")
        self.text.focus_set()
        self.numbers.redraw()

    # -- the drawing canvas ----------------------------------------------------------------------

    def _draw_canvas(self):
        c = self.canvas
        c.delete("all")
        draws = getattr(self, "last_draws", None)
        if draws is None:
            return
        width, height = c.winfo_width(), c.winfo_height()
        if width < 20 or height < 20:
            return
        margin = self.px(28)
        min_x, min_y, max_x, max_y = runtime.bounding_box(draws)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        k = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)
        off_x = (width - span_x * k) / 2.0
        off_y = (height - span_y * k) / 2.0

        def sx(x):
            return off_x + (x - min_x) * k

        def sy(y):
            return height - (off_y + (y - min_y) * k)

        axis = "#E5E7EB"
        c.create_line(0, sy(0), width, sy(0), fill=axis)
        c.create_line(sx(0), 0, sx(0), height, fill=axis)
        c.create_text(sx(0) + 4, sy(0) + 4, anchor="nw", fill=MUTED,
                      text="(0, 0)", font=self.small_mono)
        pen_width = max(1.5, 2 * self.scale)
        for d in draws[:50000]:
            if d.kind == "line":
                x1, y1, x2, y2 = d.data
                c.create_line(sx(x1), sy(y1), sx(x2), sy(y2), fill=d.color,
                              width=pen_width, capstyle="round")
            elif d.kind == "circle":
                cx, cy, r = d.data
                c.create_oval(sx(cx - r), sy(cy + r), sx(cx + r), sy(cy - r),
                              outline=d.color, width=pen_width)
            else:
                cx, cy, s = d.data
                h = s / 2.0
                c.create_rectangle(sx(cx - h), sy(cy + h), sx(cx + h),
                                   sy(cy - h), outline=d.color,
                                   width=pen_width)
        pen = getattr(self, "last_pen", None)
        if pen is not None:
            px_, py_ = sx(pen["x"]), sy(pen["y"])
            rad = math.radians(pen["heading"])
            tip = (px_ + 10 * self.scale * math.cos(rad),
                   py_ - 10 * self.scale * math.sin(rad))
            c.create_line(px_, py_, tip[0], tip[1], fill=ACCENT, width=2,
                          arrow="last")
            c.create_oval(px_ - 3, py_ - 3, px_ + 3, py_ + 3, fill=ACCENT,
                          outline=ACCENT)

    # -- the grammar tab ---------------------------------------------------------------------------

    def _fill_grammar_tab(self):
        g = grammar.get_grammar()
        w = self.grammar_text
        w.configure(state="normal")
        w.delete("1.0", "end")

        def section(title, body):
            w.insert("end", title + "\n", "heading")
            w.insert("end", body + "\n\n")

        section("Productions (%s)" % grammar.format_summary(g),
                grammar.format_productions(g))
        section("FIRST and FOLLOW", grammar.format_first_follow(g))
        section("LL(1) parsing table (cell = production number)",
                grammar.format_table(g))
        w.insert("end", "Conflict\n", "heading")
        w.insert("end", grammar.format_conflicts(g) + "\n", "conflict")
        w.configure(state="disabled")


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:           # older Windows or no shcore: ignore
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
