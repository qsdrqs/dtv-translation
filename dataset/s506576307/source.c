#include <stdio.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main()
{
	long long n, s;
	scanf("%lld", &n);
	scanf("%lld", &s);
	if (n == s) {
		printf("%lld\n", n + 1);
		fflush(stdout);
		return 0;
	}
	
	long long b, m, d;
	for (b = 2; b * b <= n; b++) {
		for (m = n, d = 0; m > 0; m /= b) d += m % b;
		if (d == s) {
			printf("%lld\n", b);
			fflush(stdout);
			return 0;
		}
	}
	
	for (d = (b - 1 < s)? b - 1: s; d >= 1; d--) {
		b = (n - (s - d)) / d;
		if (d * b + s - d == n && d < b && s - d < b) {
			printf("%lld\n", b);
			fflush(stdout);
			return 0;
		}
	}
	
	printf("-1\n");
	fflush(stdout);
	return 0;
}