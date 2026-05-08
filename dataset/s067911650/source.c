// AOJ 2082: Goofy Converter
// 2017.11.7 bal4u@uu

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

int a[1002], n, m;
char ans[1020], *p;

int bin2sz(int k, int goal)
{
	int i, c = 0;
	i = m; while (i--) {
		if (k & 1) ans[i] = '1', c++;
		else       ans[i] = '0';
		if (c > goal) return 0;
		k >>= 1;
	}
	return c == goal;
}

int check()
{
	int i, j, c;

	for (j = m, i = 1; i < n; i++, j++) {
		if (a[i] == a[i-1]) ans[j] = ans[i-1];
		else {
			ans[j] = '0'+ ('1' - ans[i-1]);
			if (ans[i-1] == '1') c = a[i-1]-1;
			else                 c = a[i-1]+1;
			if (c != a[i]) return 0;
		}
	}
	return 1;
}

int main()
{
	int i, lim;

	while (scanf("%d%d", &n, &m) && n > 0) {
		for (i = 0; i < n; i++) scanf("%d", a+i);
		lim = 1 << m;
		for (i = 0; i < lim; i++) {
			if (bin2sz(i, a[0]) && check()) break;
		}
		if (i == lim) puts("Goofy");
		else ans[n+m-1] = 0, puts(ans);
	}
	return 0;
}