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

int n, m, k;
int a[99], b[99], c[99];
void push (int x, int y, int z) {
	a[m] = x;
	b[m] = y;
	c[m] = z;
	m++;
}

int main () {
	int i;
	scanf("%d", &k);
	while ((1 << n) <= k) n++;
	for (i = n - 1; i > 0; i--) {
		push(i, i - 1, 0);
		push(i, i - 1, 1 << (i - 1));
	}
	for (i = n - 2; i >= 0; i--) {
		if ((1 << i) & k) {
			push(n - 1, i, (k >> (i + 1)) << (i + 1));
		}
	}
	printf("%d %d\n", n, m);
	for (i = 0; i < m; i++) {
		printf("%d %d %d\n", n - a[i], n - b[i], c[i]);
	}
	return 0;
}
