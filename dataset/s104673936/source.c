#include<stdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main()
{
	int n, m;
	scanf("%d %d", &n, &m);
	int i, j, k;
	int a[10];
	for (i = 0; i < m; i++)
		scanf("%d", &a[i]);
	int c[10] = { 1000000009,2,5,5,4,5,6,3,7,6 };
	int dp[10004][10];
	for (i = 0; i < 10004; i++)
		for (j = 0; j < 10; j++)
			dp[i][j] = 0;
	for (i = 0; i <= n; i++)
		dp[i][0] = -1;
	dp[0][0] = 0;
	int v[10], p;
	for (i = 1; i <= n; i++)
	{
		for (j = 0; j < m; j++)
		{
			if (i >= c[a[j]])
			{
				if (i == 10)
					i = 10;
				if (dp[i-c[a[j]]][0]>=0 && dp[i][0] < dp[i - c[a[j]]][0] + 1)
				{
					for (k = 0; k < 10; k++)
						dp[i][k] = dp[i - c[a[j]]][k];
					dp[i][0]++;
					dp[i][a[j]]++;
				}
				if (dp[i][0] == dp[i - c[a[j]]][0] + 1 && dp[i - c[a[j]]][0] >= 0)
				{
					for (k = 0; k < 10; k++)
						v[k] = dp[i - c[a[j]]][k];
					v[0]++;
					v[a[j]]++;
					p = -1;
					for (k = 9; k > 0; k--)
					{
						if (dp[i][k] > v[k])
							break;
						if (dp[i][k] < v[k])
						{
							p = 1;
							break;
						}
					}
					if (p > 0)
					{
						for (k = 0; k < 10; k++)
							dp[i][k] = v[k];
					}
				}
			}
		}
	}
	for (i = 9; i > 0; i--)
		for (j = 0; j < dp[n][i]; j++)
			printf("%d", i);
	printf("\n");
	return 0;
}