# square spiral: keep going while the side is short OR fewer than 4 turns were made
int side = 5;
int turns = 0;
pencolor #2E7D32;
while (side < 150 or turns < 4) {
    forward side;
    turn 90;
    side = side + 5;
    turns = turns + 1;
}
