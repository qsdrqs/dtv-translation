// AOJ 2106 Enegy Transporter
// 2018.3.4

#include <stdio.h>
#include <string.h>

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
	int n = 0;
	int c = getchar_unlocked();
	while (c <= ' ') c = getchar_unlocked();
	do n = (n<<3)+(n<<1) + (c & 0xf), c = getchar_unlocked();
	while (c >= '0');
	return n;
}

#define N 82
int e[82];
char dp[2][N][N];

int main()
{
	int cno, w, n, i, j, k, k1, k2, t, ans;

	cno = in(); while (cno--) {
		w = in(), n = w-1;
		for (i = 0; i < w; i++) e[i] = in();
		if (n < 2) { printf("%d\n", e[n]); continue; }

		ans = e[n];
		memset(dp, 0, sizeof(dp));
		for (k1 = 1, k2 = 0, i = 1; i < n; i++, k1 = k2, k2 = !k2) {
			memset(dp[k2], 0, sizeof(dp[k2]));
			dp[k1][e[i-1]][e[i]] = 1;
			t = e[i+1];
			for (j = 0; j < N; j++) for (k = 0; k < N; k++) {
				if (!dp[k1][j][k]) continue;
				if (!k) {
					if (i+2 < w) dp[k2][k][t] = 1;
					else if (t > ans) ans = t;
				} else {
					if (i+2 < w) dp[k2][k][t] = dp[k2][k-1][t+j] = 1;
				    else if (t+j > ans) ans = t+j;
				}
		    }
	    }
		printf("%d\n", ans);
	}
	return 0;
}
