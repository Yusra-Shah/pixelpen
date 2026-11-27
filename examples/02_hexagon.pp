# a regular hexagon: six sides, turning 60 degrees counterclockwise each time
pencolor #1E88E5;
penup;
moveto (-40, -70);
pendown;
repeat 6 {
    forward 80;
    turn 60;
}
