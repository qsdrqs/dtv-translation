#include <stdio.h>          // printf(), getchar(), scanf()
#include <ctype.h>          // isdigit()

#define MAX_N 100000

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int
main(int argc, char** argv)
{
	int n, q;
	int a[MAX_N];
	int c;
	int i;

	scanf("%d %d", &n, &q);
	c = getchar();
	for (i = 0; i < n; ++i)
	{
		while (c == ' ' || c == '\n')
			c = getchar();

		int d = 0;
		while (isdigit(c))
		{
			d = d * 10 + c - '0';
			c = getchar();
		}

		a[i] = d;
	}

	for (i = 0; i < q; ++i)
	{
		while (c == ' ' || c == '\n')
			c = getchar();

		long x = 0;
		while (isdigit(c))
		{
			x = x * 10 + c - '0';
			c = getchar();
		}

		long count = 0;
		long sum = 0;
		int s, t;
		for (s = 0, t = 0; s < n; ++s)
		{
			sum += a[s];
			while (sum > x)
				sum -= a[t++];

			count += s - t + 1;
		}

		printf("%ld\n", count);
	}

	return 0;
}