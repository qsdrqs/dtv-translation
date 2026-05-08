// AOJ 2566: Restore Calculation
// 2018.1.8 bal4u@uu

#include <stdio.h>
#include <string.h>

#define M 1000000007

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int sz;
int a[52][10], b[52][10], c[52][10];
int ha[52], hb[52], hc[52];
int dp[52][2];

void pb(int a[52][10], int *h, char *p)
{
	int i, j, k;
	char *q = p;

	while (*p > ' ') p++; sz = p-q;
	i = 0; while (--p >= q) {
		h[i] = 0;
		if (*p != '?') a[i][0] = *p & 0xf, h[i]++;
		else { k = (p == q), j = 10-k; while (j--) a[i][j] = k, k++, h[i]++; }
		i++;
	}
}

int main()
{
	int i, k, aa, bb, cc, sum, dig, ca;
	char buf[55];

	while (fgets(buf, 55, stdin) && *buf != '0') {
		pb(a, ha, buf);
		fgets(buf, 55, stdin), pb(b, hb, buf);
		fgets(buf, 55, stdin), pb(c, hc, buf);

		memset(dp, 0, sizeof(dp));
	    dp[0][0] = 1;

		for (i = 0; i < sz; i++) for (k = 0; k < 2; k++) {
			for (aa = 0; aa < ha[i]; aa++) for (bb = 0; bb < hb[i]; bb++) for (cc = 0; cc < hc[i]; cc++) {
		        sum = a[i][aa] + b[i][bb] + k;
				dig = sum % 10, ca = sum / 10;
				if (dig == c[i][cc]) {
					dp[i+1][ca] += dp[i][k];
					if (dp[i+1][ca] >= M) dp[i+1][ca] -= M;
		        }
			}
		}
		printf("%d\n", dp[sz][0]);
	}
	return 0;
}

