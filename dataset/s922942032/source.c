#include <stdio.h>          // printf(), scanf()
#include <stdlib.h>         // abs()
#include <string.h>         // memset()
#include <stdbool.h>

#define MAX_N 15
#define MAX_S (1 << MAX_N)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

const double INF = 1e10;

int n;
int s[MAX_N], l[MAX_N], v[MAX_N];
double dp[MAX_N][MAX_S];
int w[MAX_N][MAX_S];
short prev[MAX_N][MAX_S][2];
int ord[MAX_N];

int
main(int argc, char **argv)
{
	scanf("%d", &n);
	for (int i = 0; i < n; ++i)
		scanf("%d%d%d", &s[i], &l[i], &v[i]);

	memset(prev, -1, sizeof(prev));
	int S = 1;
	for (int i = 0; i < n; i++, S <<= 1)
		w[i][S] = v[i];

	int e = 1 << n;
	for (int k = 0; k < e; ++k)
	{
		S = 1;
		for (int i = 0; i < n; ++i, S <<= 1)
		{
			if (k & S)
				continue;

			int t = k | S;
			for (int j = 0; j < n; ++j)
			{
				if (i == j || w[j][k] == 0)
					continue;

				int d = abs(l[i] - l[j]);
				double x = dp[j][k] + (d * (7 + 2 * w[j][k])) / 200.0;
				if (dp[i][t] == 0 || x < dp[i][t])
				{
					dp[i][t] = x;
					w[i][t] = w[j][k] + v[i];
					prev[i][t][0] = j;
					prev[i][t][1] = k;
				}
			}
		}
	}

	double min = INF;
	int u = 0;
	for (int i = 0; i < n; ++i)
	{
		double y = dp[i][e - 1];
		if (y == 0)
			continue;

		if (y < min)
		{
			min = y;
			u = i;
		}
	}

	ord[0] = u;
	int v = e - 1;
	for (int k = 1; k < n; ++k)
	{
		ord[k] = prev[u][v][0];
		v = prev[u][v][1];
		u = ord[k];
	}

	for (int i = n - 1; i >= 0; --i)
		printf("%d%c", s[ord[i]], (i != 0) ? ' ' : '\n');

	return 0;
}