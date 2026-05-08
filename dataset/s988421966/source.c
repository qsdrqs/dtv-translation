// AOJ 2261: [[iwi]]
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

char s[17], *p, *q;
int c[17][17];

int check(int i, int j)
{
	int k;
	char a[2][6] = {{ '(', ')', '{', '}', '[', ']' },
					{ ')', '(', '}', '{', ']', '[' }};
	for (k = 0; k < 6; k++)
		if (*(p-i) == a[0][k] && *(q+j) == a[1][k]) return 1;
	return 0;
}

int LCS(int m, int n)
{
	int i, j;

	for (i = 1; i <= m; i++) for (j = 1; j <= n; j++) {
	    if (check(i-1, j-1)) c[i][j] = c[i-1][j-1] + 1;
		else {
			if (c[i-1][j] >= c[i][j-1]) c[i][j] = c[i-1][j];
			else c[i][j] = c[i][j-1];
		}
	}
	return c[m][n];
}

int main()
{
	int n, ans;

	scanf("%s", s); n = strlen(s);
	p = s; while (*p != 'w') p++;
	q = p; q+=2, p-=2;
	ans = LCS(p-s+1, n-(p-s)-4);
	printf("%d\n", 2*ans+3);
	return 0;
}