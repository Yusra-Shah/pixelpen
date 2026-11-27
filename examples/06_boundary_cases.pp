# boundary cases: everything here is legal (one warning for repeat 0)
int zero = 0;
int neg = 0 - 7;
int q = neg / 2;                 # -3: division truncates toward zero
int r = neg % 2;                 # -1: the remainder keeps the left sign
int mix = 2 + 3 * 4 - 10 / 3 % 2;
repeat 0 { forward 10; }         # warning: the body never runs
circle (0, 0), 0;                # radius 0 is allowed
square (0, 0), zero;             # side 0 is allowed
{ }                              # an empty block
{ { { forward 1; } } }           # nested blocks
if (q == 0 - 3 and r == 0 - 1)
    pencolor #00AA00;
else
    pencolor #AA0000;
if (not (zero != 0))
    forward 5;
color c1 = #ABCDEF;
color c2 = #abcdef;
if (c1 == c2)
    turn 45;                     # hex digits are not case sensitive
if (100 < 100 or 100 <= 100)     # the edge of a range check
    forward 20;
# end of file comment without a newline
#