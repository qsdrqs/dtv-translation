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

int main()
{
	char A[200001];
	scanf("%s", A);
	
	int i, j, k, rest[200001], count[26] = {}, num = 0;
	char ans[10000] = {};
	for (i = 0; A[i] != 0; i++);
	for (rest[i--] = -1, k = 0; i >= 0; i--) {
		rest[i] = k;
		if (count[A[i] - 'a'] == 0) num++;
		count[A[i] - 'a']++;
		if (num == 26) for (j = 0, num = 0, k++; j < 26; j++) count[j] = 0;
	}
	
	int l = 0;
	while (1) {
		for (j = 0; j < 26; j++) count[j] = 0;
		for (i++; rest[i] == k; i++) count[A[i] - 'a']++;
		for (j = 0; j < 26; j++) if (count[j] == 0) break;
		ans[l++] = 'a' + j;
		for (k--; A[i] != 0 && A[i] != 'a' + j; i++);
		if (A[i] == 0) break;
	}
	
	printf("%s\n", ans);
	fflush(stdout);
	return 0;
}