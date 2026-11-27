# points are written (x, y); line joins two points, circle and square are centered
point left = (-100, -60);
point right = (100, -60);
point top = (0, 100);
pencolor #C62828;
line left, right;
line right, top;
line top, left;
pencolor #283593;
point center = (0, 0 - 60 / 3);
circle center, 45;
square center, 90;
# moveto relocates the pen without drawing, forward then draws from there
penup;
moveto top;
pendown;
turn 270;
forward 40;
