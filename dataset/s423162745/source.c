// AOJ 2170: Marked Ancestor
// 2018.1.2 bal4u@uu

#include <stdio.h>
#include <string.h>

#define INF 0x01010101
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { int i, v; } T;
T tbl[100003]; int sz;
int p[100003];
int mk[100003];

//#define getchar_unlocked()  getchar()
int in()
{
	int n, c;

//	while ((c = getchar_unlocked()) < '0');
	c = getchar_unlocked();
	n = 0;
	do n = (n<<3)+(n<<1) + (c & 0xf), c = getchar_unlocked();
	while (c >= '0');
	return n;
}

int find(int v, int i)
{
	if (mk[v] < i) return v;
	return p[v] = find(p[v], i);
}

int main()
{
	int N, Q, i, cmd, v;
	long long ans;

	while (N = in()) {
		Q = in();
		p[1] = 1; for (i = 2; i <= N; i++) p[i] = in();

		memset(mk, INF, sizeof(mk));
		mk[1] = 0;

		sz = 0;
		for (i = 1; i <= Q; i++) {
			cmd = getchar_unlocked(); getchar_unlocked();
			v = in();
			if (cmd == 'M') { if (mk[v] == INF) mk[v] = i; }
			else tbl[sz].i = i, tbl[sz++].v = v;
		}

		ans = 0;
		while (sz--) ans += find(tbl[sz].v, tbl[sz].i);
		printf("%lld\n", ans);
	}
	return 0;
}
