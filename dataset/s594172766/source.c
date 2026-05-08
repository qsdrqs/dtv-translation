// Aizu Vol-10 1062: It's our delight!!
// 2017.8.18 bal4u@uu

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

int cnt[3], ok[3];
char *a[3] = { "lunch", "dinner", "midnight" };
// ???11:00-14:59, ???18:00-20:59, ??±???21:00-01:59
int tt[3][2] = { { 660, 899 } , { 1080, 1259 }, { 1260, 1559 } };

int main()
{
	int n, hh, mm, MM;
	int i, j, t;

	while (scanf("%d", &n) && n) {
		for (j = 0; j < 3; j++) cnt[j] = ok[j] = 0;
		for (i = 0; i < n; i++) {
			scanf("%d%*c%d%d", &hh, &mm, &MM);
			if (hh <= 2) hh += 24;
			if (MM >= mm) MM += hh * 60;
			else          MM += (hh + 1) * 60;
			t = hh * 60 + mm;
			for (j = 0; j < 3; j++) {
				if (tt[j][0] <= t && t <= tt[j][1]) {
					cnt[j]++;
					if (MM - t <= 8) ok[j]++;
				}
			}
		}
		for (j = 0; j < 3; j++) {
			printf("%s ", a[j]);
			if (cnt[j] == 0) puts("no guest");
			else printf("%d\n", ok[j] * 100 / cnt[j]);
		}
	}
	return 0;
}