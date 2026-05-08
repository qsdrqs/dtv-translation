// AOJ 0364: Dungeon
// 2017.12.20

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

int max[100001];
char buf[30], *p;

int in()
{
	int n = 0;
	while (*p >= '0') n = (n<<3) + (n<<1) + (*p++ & 0xf);
	p++;
	return n;
}

int main()
{
	int w, h, n, x, y, ans;

	fgets(p=buf, 30, stdin);
	w = in(), h = in(), n = in();
	while (n-- > 0) {
		fgets(p=buf, 20, stdin);
		x = in(), y = in();
		if (y > max[x]) max[x] = y;
	}

	ans = 0x7fffff;
	x = w, y = 0; while (x--) {
		if (x+y < ans) ans = x+y;
		if (max[x] > y) y = max[x];
	}
	printf("%d\n", ans);
	return 0;
}