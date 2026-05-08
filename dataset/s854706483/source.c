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
	int i, j;
	int n;
	int a[10004];
	int ans[50004];
	int sum;
	for (i = 0;; i++)
	{
		scanf("%d", &n);
		if (n == 0)
			break;
		for (j = 0; j < n; j++)
			scanf("%d", &a[j]);
		sum = 0;
		for (j = 0; j < n; j++)
			sum += a[j];
		ans[i] = 0;
		for (j = 0; j < n; j++)
			if (sum >= n * a[j])
				ans[i]++;
	}
	for (j = 0; j < i; j++)
		printf("%d\n", ans[j]);
	return 0;
}
