# ten syntax errors, each reported once; phrase-level recovery keeps parsing
int a = 40
color c = #FF5733;
if (a > 3 {
    forward 10;
}
repeat 4 forward 10;
turn 60 90;
point p = (1, 2, 3);
int circle = 5;
if (a < 5 < 9) turn 1;
forward 10; else turn 5;
}
repeat 3 {
    turn 10;
# 1 missing ';' (line 2)        2 missing ')' (line 4)
# 3 loop body without braces    4 'turn 60 90;' missing operator
# 5 point with 3 coordinates    6 keyword used as a variable name
# 7 chained comparison          8 else without if
# 9 unmatched '}'               10 block never closed (end of file)
