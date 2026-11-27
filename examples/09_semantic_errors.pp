# semantic errors: the program parses, but the types and names are wrong
int count = 5;
color tint = #3366CC;
point home = (0, 0);
int count = 7;                   # already declared
int broken = tint + 2;           # arithmetic on a color
color wrong = 12;                # int stored in a color
forward ghost;                   # ghost is not declared (reported once)
turn ghost + 1;                  # ...and not again here
if (count) forward 5;            # a condition must be a comparison
if (count and count > 1) turn 3; # and needs bool operands
if (not count) turn 4;           # not needs a bool operand
while (tint < tint) { turn 1; }  # < needs ints
if (count == tint) turn 2;       # == needs two ints or two colors
moveto count;                    # moveto needs a point
pencolor home;                   # pencolor needs a color
circle home, tint;               # the radius must be an int
line home, 5;                    # line needs two points
point odd = (tint, 1);           # coordinates must be int
int bad = 10 / 0;                # division by constant 0
repeat 0 { forward 1; }          # warning: the loop never runs
count = tint;                    # assignment changes the type
