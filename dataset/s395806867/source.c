// AOJ 2708: ABC Gene
// 2017.11.26 bal4u@uu

#include <stdio.h>
#include <stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

char s[2][5002];
int f['C'+1];

int main()
{
	int n, i, k1, k2, n2;
	char x, *p, *q;

	fgets(p=s[0], 5002, stdin);
	while (*p > ' ') f[*p++]++;
	n = p - s[0];

	for (i = 'A'; i <= 'C'; i++) if (!f[i]) break;
	if (i <= 'C') goto no;
	for (k1 = 0, k2 = 1; n > 3; k1 = k2, k2 = !k2) {
		p = s[k1], q = s[k1]+n-3;
		if      (*p == 'A' && *(p+1) == 'B' && *(p+2) == 'C') x = 'A';
		else if (*q == 'A' && *(q+1) == 'B' && *(q+2) == 'C') x = 'C';
		else x = 'B';

		q = s[k2]; while (*p > ' ') {
			if (*p == 'A' && *(p+1) == 'B' && *(p+2) == 'C') *q++ = x, p+=3;
			else *q++ = *p++;
		}
		*q = 0;
		n2 = q-s[k2];
//printf("n %d -- %s\n", n2, s[k2]);
		if (n - n2 < 2) goto no;
		n = n2;

		p = s[k2], q = s[k1]; while (*p > ' ') {
			if (*p == x) {
				if (*q != 'A' || *(q+1) != 'B' || *(q+2) != 'C') goto no;
				q += 2;
			} else if (*q != *p) goto no;
			p++, q++;
		}
	}

	if (n == 3) {
		for (i = 0; i < 3; i++) if (s[k1][i] != i+'A') break;
		if (i == 3) { puts("Yes"); return 0; }
	}
no: puts("No");
	return 0;
}