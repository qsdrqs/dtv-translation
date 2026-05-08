// AOJ 2335: 10-Year-Old Dynamic Programming
// 2017.11.27 bal4u@uu

#include <stdio.h>

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

long long fact[2020001];

int extended_gcd(int a, int b, int *x, int *y)
{
	int d;

	if (b == 0) { *x = 1; *y = 0; return a; }
	d = extended_gcd(b, a % b, y, x);
	*y -= a / b * (*x);
	return d;
}

long long inverse(int a)
{
    int x, y;
    if (extended_gcd(a, M, &x, &y) == 1) return (x + M) % M;
    return 0;
}

long long comb(int n, int k)
{
    if (n < 0 || k < 0 || n < k) return 0;
    return fact[n] * inverse((fact[k]*fact[n-k]) % M) % M;
}

int main()
{
	int n, m, k, i, j, ii, jj, kk;
	long long ans, r, c;

	for (fact[0] = 1, i = 1; i < 2020001; i++) fact[i] = (fact[i-1]*i) % M;

	scanf("%d%d%d", &n, &m, &k);

    ans = 0; kk = n + m + (k << 1);
    for (i = 0; i <= k; i++){
        j = k-i, ii = n + (i << 1), jj = m + (j << 1);
        r = (comb(ii, i) - comb(ii, i-1) + M) % M;
        c = (comb(jj, j) - comb(jj, j-1) + M) % M;
        ans = (ans + (r*c) % M * comb(kk, ii)) % M;
    }
    printf("%lld\n", ans);
}