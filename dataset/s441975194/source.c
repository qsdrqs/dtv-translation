// AOJ 1222: Telescope
// 2017.10.17 bal4u@uu

#include <stdio.h>
#include <string.h>
#include <math.h>

#define PI2 6.283185307179586476925286766559  // 2*PI

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

double p[42];
double area[42][42][42];
double dp[42][42][42];

int main()
{
	int n, m, i, j, k, l;
	double ans, a;

	while (scanf("%d%d", &n, &m) && n > 0) {
		for (i = 0; i < n; i++) scanf("%lf", p+i);
//		memset(area, 0, sizeof(area));
		for (i = 0; i < n; i++) for (j = i+1; j < n; j++) for (k = j+1; k < n; k++)
			area[i][j][k] = 0.5*(sin((p[j]-p[i])*PI2) + sin((p[k]-p[j])*PI2) + sin((p[i]-p[k])*PI2));

		for (i = 0; i < n; i++) for (j = i+1; j < n; j++) for (k = 2; k <= m; k++) dp[i][j][k] = -1;
		for (i = 0; i < n; i++) for (j = i+1; j < n; j++) dp[i][j][2] = 0;
		ans = 0;
		for (i = 0; i < n; i++) for (l = 2; l < m; l++) for (j = i+1; j < n; j++) for (k = j+1; k < n; k++) {
			if (dp[i][j][l] < 0) continue;
			a = dp[i][j][l] + area[i][j][k];
			if (a > dp[i][k][l+1]) {
				dp[i][k][l+1] = a;
				if (l+1 <= m && a > ans) ans = a;
			}
		}
		printf("%.6lf\n", ans);
    }
	return 0;
}