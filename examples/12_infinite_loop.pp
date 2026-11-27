# infinite loop: x only grows, so (x > 0) never becomes false
# the interpreter stops after 200000 instructions and reports an error
int x = 1;
pencolor #D81B60;
while (x > 0) {
    forward 1;
    turn 1;
    x = x + 1;
}
