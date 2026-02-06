#include <stdio.h>

int clamp_value(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

int addOffset(int x, int offset) {
    return clamp_value(x + offset, -100, 100);
}

int main(void) {
    int x = 0, offset = 0;
    if (scanf("%d %d", &x, &offset) != 2) {
        return 1;
    }
    printf("%d\n", addOffset(x, offset));
    return 0;
}
