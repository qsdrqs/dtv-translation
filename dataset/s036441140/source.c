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
	int asumikana, sakuraayane;
	int mimorisuzuko;
	if(scanf("%d%d", &asumikana, &sakuraayane) != 2) return 1;
	for(mimorisuzuko = 0; mimorisuzuko < asumikana - 1; mimorisuzuko++) {
		printf("%d ", mimorisuzuko <= asumikana / 2 ? 0 : sakuraayane);
	}
	printf("%d\n", sakuraayane);
	return 0;
}