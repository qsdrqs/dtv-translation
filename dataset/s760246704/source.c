// Aizu Vol-2 0266: Aka-beko and 40 Thieves
// 2017.8.6

#include <stdio.h>
#include <ctype.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

char *gets();
char buf[150], *p;

int e[6][2] = {
	{ 1, 2 }, { -1, 3 }, { 1, -3 }, { 4, 5 }, { 5, 2 }, { 2, 1 } };

int main()
{
	int s;

	while (1) {
		gets(p = buf); while (isspace(*p)) p++;
		if (*p == '#') break;
		s = 0;
		while (*p) {
			if (*p == '0') { if ((s = e[s][0]) < 0) goto NO; }
			else { if ((s = e[s][1]) < 0) goto NO; }
			p++;
		}
		if (s != 5) {
NO:			puts("No");
		} else puts("Yes");
	}
	return 0;
}