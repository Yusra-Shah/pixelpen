int size = 40
color c = #FF5733;
pencolor c;
# Compile this twice.
#   Recovery = phrase-level : ONE error on line 1 (missing ';'), nothing else.
#   Recovery = panic only   : the error is reported on line 2, panic mode skips
#                             the whole 'color c = #FF5733' declaration, and
#                             the parser then accepts the ';' of that line.
#                             Semantic analysis (run only in this mode) then
#                             reports a FALSE error: 'c' is not declared.
