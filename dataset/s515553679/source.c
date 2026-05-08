// AOJ 2767: AddMul
// 2017.10.10 bal4u@uu

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

char s[500];
int f['z'+1];
int c[10];

int main()
{
	int n, i, term, ans;
	char *p;

	scanf("%d%s", &n, s);
	p = s; while (*p) f[*p]++, p+=2;
	for (i = 'a'; i <= 'z'; i++) c[f[i]]++;

	ans = term = c[1];
	for (i = 2; i < 10; i++) {
		if      (c[i] == 1) ans += 3, term++;
		else if (c[i] >  1) ans += 2*c[i]+3, term++;
	}
	printf("%d\n", ans + term - 1);
	return 0;
}