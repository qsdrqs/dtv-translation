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
	int N, d;
	int i;
	int gosennchouenn = 0;
	if (scanf("%d%d", &N, &d) != 2) return 1;
	for (i = 0; i < N; i++) {
		int p;
		if (scanf("%d", &p) != 1) return 1;
		if (p > d) gosennchouenn += p - d;
	}
	if (gosennchouenn >= 1) {
		printf("%d\n", gosennchouenn);
	} else {
		puts("kusoge");
	}
	return 0;
}

