# runtime error: the divisor is a variable, so only the interpreter can see it is zero
int steps = 3;
int spare = steps - 3;
pencolor #00897B;
forward 100;
turn 90;
forward 100 / spare;
forward 50;
# The drawing so far is kept, the log shows the error, and execution stops.
# Other runtime errors to try (replace the division line above):
#   circle (0, 0), spare - 5;      negative size
#   int x = 10 % spare;            modulo by zero
