// AOJ 1092 Make KND So Fat
// 2018.2.3 bal4u

#include <stdio.h>
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

int k[101], w[101][51], p[101][51];
int f[101];
int dp[301];

//#define getchar_unlocked()  getchar()
int in()
{
	int n = 0;
	int c = getchar_unlocked();
	do n = (n<<3)+(n<<1) + (c & 0xf), c = getchar_unlocked();
	while (c >= '0');
	return n;
}

int main()
{
	int s, d, m, i, j, t, ans, money;

	do {
		s = in(), d = in(), m = in();
		for (i = 0; i < s; i++) {
			k[i] = in();
			for (j = 0; j < k[i]; j++) w[i][j] = in(), p[i][j] = in();
		}
		for (i = 0; i < d; i++) f[i] = in();

		memset(dp, 0, sizeof(dp));

		for (i = 0; i < d; i++) {
			s = f[i];
			for (j = 0; j < k[s]; j++) {
				for (t = m; t >= 0; t--) if (t + p[s][j] <= m) {
					int x = dp[t] + w[s][j];
					if (x > dp[t + p[s][j]]) dp[t + p[s][j]] = x;
				}
			}
		}

		ans = money = 0;
		for (i = 0; i <= m; i++) if (dp[i] > ans) ans = dp[i], money = i;
		printf("%d %d\n", ans, money);
	} while (getchar_unlocked() >= 0);
	return 0;
}
