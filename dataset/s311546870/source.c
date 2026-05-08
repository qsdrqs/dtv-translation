// AOJ 2717: Where is the Boundary
// 2018.1.5 bal4u@uu

#include <stdio.h>

#define MAX 10003
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int se[MAX], sw[MAX], w[MAX];
char d[MAX];

int main()
{
	int n, m, i, j, x, total_w, min, ans;
	char *p;

	fgets(d, 15, stdin), sscanf(d, "%d%d", &n, &m);
	se[0] = sw[0] = total_w = 0;
	j = m; while (j--) {
		fgets(p=d, MAX, stdin);
		for (i = 1; *p > ' '; i++) {
			if ((*p++ >> 1) & 1) w[i]++, total_w++;
		}
	}
	for (i = 1; i <= n; i++) se[i] = se[i-1]+(m-w[i]), sw[i] = sw[i-1]+w[i];
	se[n+1] = se[n], sw[n+1] = sw[n];

	ans = 0, min = 0x7fffff;
	for (i = 0; i <= n; i++) {
		x = se[i]+total_w-sw[i];
		if (x < min) min = x, ans = i;
	}
	printf("%d %d\n", ans, ans+1);
	return 0;
}
