// AOJ 2507 Computer Onesan
// 2018.2.7 bal4u
 
#include <stdio.h>

#define M 1000000

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int dp[102] = {1,4,12,38};

int main()
{
	int n, m, i;

	scanf("%d%d", &n, &m);
    if (m == 1) for (i = 1; i <= n; i++) dp[i] = (dp[i-1]<<1) % M;
    else {
		for (i = 4; i <= n; i++) {
			dp[i] = dp[i-4] + (dp[i-3]<<1) - dp[i-2]*3 + (dp[i-1]<<2);
			dp[i] %= M;	if (dp[i] < 0) dp[i] += M;
		}
	}
    printf("%d\n", dp[n]);
	return 0;
}

