// AOJ 374 Paper Fortune
// 2018.4.1 bal4u

#include <stdio.h>
#include <string.h>
#include <math.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int  n;
char s[100005];
int  f[10];
int  diff;
int  mi, ma;

int mima(char *s)
{
	int a = 10* (*s) + *(s+1);
	if (a < mi) mi = a;
	if (a > ma) ma = a;
	return ma-mi > diff;
}

int check(int len)
{
	int w = len-2, k, d;
	char *p;
	
	mi = 100, ma = 0, p = s+len;
	for (k = len; k < n; k += len) {
		if (memcmp(p, s, w)) return 0;
		if (k == len) mima(s+w);
		if (mima(p+w)) return 0;
		p += len;
	}
	d = ma-mi;
	if (d < diff) diff = d;
	return !diff;
}

int main()
{
	int i, w, a, max, min;
	char *p;
	
	fgets(p=s, sizeof(s), stdin);
	while (*p >= '0') { *p &= 0xf, f[*p]++, p++; }
	*p = 0;
	n = p - s;
	min = 10, max = 0;
	for (i = 1; i < 10; i++) if (f[i]) {
		if (i < min) min = i;
		if (i > max) max = i;
	}
	diff = max-min;
	if (n ==2 || !diff) goto done;
	
	if (n >= 4) {
		w = sqrt(n);
		for (i = 2; i <= w; i++) {
			if (n % i) continue;
			if (check(i)) goto done;
			if (n == i*i) continue;
			if (check(n/i)) goto done;
		}
	}

	max = 0; min = 99;
	for (p = s; *p > 0; p++) {
		if (*p == 1) {
			if (*(p+1) > 0) {
				a = 10 + *++p;
				if (a < min) min = a;
				if (a > max) max = a;
			} else min = 1;
		} else {
			if (*p < min) min = *p;
			if (*p > max) max = *p;
		}
		if (max-min > diff) break;
	}
	if (max-min < diff) diff = max-min;
done: printf("%d\n", diff);
	return 0;
}

				
