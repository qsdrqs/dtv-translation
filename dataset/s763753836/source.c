// AOJ 1589 Unhappy Class
// 2018.4.18 bal4u

#include <stdio.h>

// バッファを経ずstdinから数値を得る
//#define getchar_unlocked()  getchar()
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int in()
{
	int n = 0, c = getchar_unlocked();
	do n = 10*n + (c & 0xf), c = getchar_unlocked(); while (c >= '0');
	return n;
}

int dp[45][45];
int hi[45], k[45][45], t[45][45];

int main()
{
	int N, M, L, da, i, j, lim;

	N = in(), M = in(), L = in();
	while (M--) {
		da = in(), da = da*N + in()-1;
		i = hi[da]++;
		k[da][i] = in();
		t[da][i] = in();
	}

	lim = 5*N;
	for (da = 0; da < lim; da++) for (i = 0; i <= L; i++) {
		if (i < L) {
			for (j = 0; j < hi[da]; j++) {
				int x =  dp[da][i] + t[da][j];
				if (x > dp[da+k[da][j]][i+1]) dp[da+k[da][j]][i+1] = x;
			}
		}
		if (dp[da+1][i] < dp[da][i]) dp[da+1][i] = dp[da][i];
	}
	printf("%d\n", dp[lim][L]);
	return 0;
}
