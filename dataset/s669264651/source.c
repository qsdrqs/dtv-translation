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

int factorize(long long n, long long p[], int m[])
{
	int k;
	long long i;
	for (i = 2, k = 0; i * i <= n; i++) {
		if (n % i != 0) continue;
		p[k] = i;
		for (m[k] = 0; n % p[k] == 0; m[k]++, n /= p[k]);
		k++;
	}
	if (n > 1) {
		p[k] = n;
		m[k++] = 1;
	}
	return k;
}

// Find an integer x such that ax + by = c with some integer y
long long solve(long long a, long long b, long long c)
{
	if (b % a == 0) return c / a;
	else return (c - solve(b % a, a, c % a) * b) / a;
}

int main()
{
	long long N;
	scanf("%lld", &N);
	if (N == 1) {
		printf("1\n");
		fflush(stdout);
		return 0;
	}

	long long p[101];
	int m[101], k = factorize(N * 2, p, m);
	
	int i, j, l[101] = {};
	long long x = 1, y, ans = N * 2;
	__int128 tmp;
	m[k] = 1;
	while (l[k] == 0) {
		y = N * 2 / x;
		tmp = solve(x, y, 1);
		if (tmp < 0) tmp = (tmp % (N * 2) + N * 2) % (N * 2);
		tmp = (x * tmp + N * 2 - 1) % (N * 2);
		if (tmp > 0 && ans > tmp) ans = tmp;
		
		for (i = 0; i < k && l[i] == m[i]; i++);
		for (j = 0; j < m[i]; j++) x *= p[i];
		for (l[i] = m[i], i--; i >= 0; l[i--] = 0) {
			for (j = 0; j < m[i]; j++) x /= p[i];
		}
	}
	printf("%lld\n", ans);
	fflush(stdout);
	return 0;
}