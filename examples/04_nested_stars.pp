# three nested five-pointed stars, each one smaller and in its own color
# the else below belongs to the NEAREST if (the inner one), not the outer one
int size = 160;
int level = 0;
color violet = #6A1B9A;
color orange = #EF6C00;
repeat 3 {
    penup;
    moveto (0 - size / 2, 0 - size / 2);
    pendown;
    if (level > 0)
        if (level > 1)
            pencolor orange;
        else
            pencolor violet;
    repeat 5 {
        forward size;
        turn 144;
    }
    size = size / 2;
    level = level + 1;
}
