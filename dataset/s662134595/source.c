// AOJ 1015: Dominating Set
// 2018.1.18 bal4u

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int n, ans;
int to[31][31], hi[31];
char black[31];

//#define getchar_unlocked()  getchar()
int in()
{
	int n = 0;
	int c = getchar_unlocked();
	do n = (n<<3)+(n<<1) + (c & 0xf), c = getchar_unlocked();
	while (c >= '0');
	return n;
}

int check()
{
	int i, j;

	for (i = 0; i < n; i++) {
		if (black[i]) continue;
		for (j = 0; ; j++) {
			if (j == hi[i]) return 0;
			if (black[to[i][j]]) break; 
		}
	}
	return 1;
}

void calc(int k, int cost)
{
	if (cost >= ans) return;

	if (k == n) {
		if (check()) ans = cost;
		return;
	}

	black[k] = 0; calc(k+1, cost);
	black[k] = 1; calc(k+1, cost+1);
}

int main()
{
	int m, a, b;

	while (n = in()) {
		memset(hi, 0, sizeof(hi));
		m = in(); while (m--) {
			a = in(), b = in();
			to[a][hi[a]++] = b, to[b][hi[b]++] = a;
		}

		ans = n;
		calc(0, 0);
		printf("%d\n", ans);
	}
	return 0;
}
