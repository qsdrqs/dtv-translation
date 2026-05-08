// AOJ 2877 Aquarium
// 2018.4.15 bal4u
 
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define INF 0x33
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

long long s[502];
double dp[502][502];

// バッファを経ずstdinから数値を得る
//#define getchar_unlocked()  getchar()
int in()
{
	int n = 0, c = getchar_unlocked();
	do n = 10*n + (c & 0xf), c = getchar_unlocked(); while (c >= '0');
	return n;
}

int main()
{
	int N, M, i, j, k;

	N = in(), M = in();
	for (i = 1; i <= N; i++) s[i] = s[i-1] + in();
	memset(dp, -INF, sizeof(dp));
	for (i = 1; i <= N; i++) dp[i][1] = (double)s[i]/i;

	for (i = 1; i <= N; i++) for (j = 1; j < M; j++) if (dp[i][j] >= 0) {
		for (k = i+1; k <= N; k++) {
			double x = dp[i][j] + (double)(s[k]-s[i])/(k-i);
			if (dp[k][j+1] < x) dp[k][j+1] = x;
		}
	}
	printf("%.8lf\n", dp[N][M]);
	return 0;
}
