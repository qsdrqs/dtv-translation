// AOJ 2187: Card Game
// 2017.11.6 bal4u@uu

#include <stdio.h>
#include <string.h>
#define TM 0
#if TM
#include <time.h>
#endif

#define SUM 171		// =19*9
#define HALF 86		// =SUM/2+1
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int g[10], j[10];
int f[10][SUM+1][1<<9], p[10];

int rec(int i, int sg, int combi)
{
	int k, r;

	if (i == 9) return sg >= HALF;
	if (f[i][sg][combi] >= 0) return f[i][sg][combi];
	if (sg >= HALF) return f[i][sg][combi] = p[9-i];
	
	r = 0;
	for (k = 0; k < 9; k++) {
		if (combi & (1<<k)) {
			if (g[i] > j[k]) r += rec(i+1, sg+g[i]+j[k], combi^(1<<k));
			else             r += rec(i+1, sg, combi^(1<<k));
		}
	}
	return f[i][sg][combi] = r;
}

int main()
{
	int t, i;
	double x;

#if TM
	clock_t start, end;
	start = clock();
#endif
	for (p[0] = 1, i = 1; i <= 9; i++) p[i] = i*p[i-1];

	scanf("%d", &t);
	while (t-- > 0) {
		for (i = 0; i < 9; i++) scanf("%d", g+i);
		for (i = 0; i < 9; i++) scanf("%d", j+i);
		memset(f, -1, sizeof(f));
		x = rec(0, 0, (1<<9)-1) * 1.0/p[9];
		printf("%.5lf %.5lf\n", x, 1-x);
	}
#if TM
	end = clock();
	printf("time %lf\n", (double)(end-start)/CLOCKS_PER_SEC);
#endif
	return 0;
}