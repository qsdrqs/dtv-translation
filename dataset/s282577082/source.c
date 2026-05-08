// AOJ 2669: A-Z Cat
// 2017.10.11 bal4u@uu

#include <stdio.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

char s[22];
char ans[22];

int main()
{
	char *p, *q;

	scanf("%s", s); p = s, q = ans;
	while (*p) {
		if (*p == 'A') {
			p++; while (*p && *p != 'Z') p++;
			if (!*p) break;
			*q++ = 'A', *q++ = 'Z';
		}
		p++;
	}
	if (q == ans) puts("-1");
	else { *q = 0; puts(ans); }
	return 0;
}