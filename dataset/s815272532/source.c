#include <stdio.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main(void) {
	int H, W, X, Y;
	if (scanf("%d%d%d%d", &H, &W, &X, &Y) != 4) return 1;
	puts((H * W) % 2 == 1 && (X + Y) % 2 == 1 ? "No" : "Yes");
	return 0;
}

