// AOJ 2904: GuruGuru
// 2019.2.23 bal4u

#define _CRT_SECURE_NO_WARNINGS
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

char S[1005], *s;

int main()
{
	int dir, f, ans;

	scanf("%s", s = S);
	dir = f = ans = 0;
	while (*s) {
		if (*s++ == 'L') dir = (dir + 3) % 4;
		else {
			dir = (dir + 1) % 4;
			f |= 1 << dir;
		}
		if (dir == 0) {
			if (f == 0xf) ans++;
			f = 0;
		}
	}
	printf("%d\n", ans);
	return 0;
}
