// Aizu 2049: Headstrong Student
// 2017.9.24 bal4u@uu

#include <stdio.h>
#include <string.h>

#define MAX 1000000
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int tbl[MAX+2];

int main()
{
	int x, y, k, r;

	while (scanf("%d%d", &x, &y) && x > 0) {
		memset(tbl, -1, sizeof(tbl));
		tbl[x] = 0;
		for (k = 1; ; k++) {
			x *= 10;
			if ((r = x % y) == 0) {
				printf("%d 0\n", k);
				break;
			}
			if (tbl[r] >= 0) {
				printf("%d %d\n", tbl[r], k - tbl[r]);
				break;
			}
			tbl[r] = k, x = r;
		}
	}
	return 0;
}