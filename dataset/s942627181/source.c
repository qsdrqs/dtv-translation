// AOJ 0352: Forecast of Forces
// 2017.10.26 bal4u@uu
// 2017.11.14

#include <stdio.h>

#define ABS(a) ((a)>=0?(a):-(a))
#define MAX(a,b) ((a)>=(b)?(a):(b))

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int w, h;
long long map[1002][1002];
long long dp[1002][1002];

long long score(int r, int c)
{
	long long x = map[r+1][w] - (map[r+1][c] << 1);
	if ((r+c) & 1) return -x;
	return x;
}

char buf[6500], *p;
int getint()
{
	int n = 0;
	if (*p == '-') {
		p++; while (*p >= '0') n = (n<<3) + (n<<1) + (*p++ & 0xf);
		return -n;
	}
	while (*p >= '0') n = (n<<3) + (n<<1) + (*p++ & 0xf);
	return n;
}

int main()
{
	int r, c;

	fgets(p=buf, 20, stdin), w = getint(), p++, h = getint();
	for (r = 1; r <= h; r++) {
		fgets(p=buf, 6500, stdin);
		for (c = 1; c <= w; c++) {
			map[r][c] = map[r][c-1] + getint(); p++;
		}
	}
	for (r = h; r >= 0; r--) for (c = w; c >= 0; c--) {
		if (r == h); // dp[r][c] = 0;
		else if (c == w) dp[r][c] = score(r, c) - dp[r+1][c];
		else             dp[r][c] = MAX(-dp[r][c+1], score(r, c) - dp[r+1][c]);
	}
	printf("%lld\n", ABS(dp[0][0]));
	return 0;
}