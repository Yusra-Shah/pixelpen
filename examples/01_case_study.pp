# flower of squares and circles
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
