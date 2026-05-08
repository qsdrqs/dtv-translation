// Aizu 2273: Shiritori
// 2017.9.22 bal4u@uu

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

char str[10];
int f[128];

int main()
{
	int  z;
	char q[5] = "aabz";

	z = 0;
	for (q[1] = 'a'; q[1] <= 'z'; q[1]++) for (q[2] = 'a'; q[2] <= 'z'; q[2]++) {
		printf("?%s\n", q);	fflush(stdout);	scanf("%s", str);
		if (*str != 'z') goto Done;
		if (str[1] == 0) { if (z) goto Done; else z = 1; *q = str[0]; }
		else             { if (f[str[1]]) goto Done; else f[str[1]] = 1; *q = str[1]; }
	}
Done:
	puts("!OUT");
	return 0;
}