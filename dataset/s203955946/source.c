// AOJ 1050 The Last Dungeon
// 2018.3.4

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define QMAX 1000
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { short s; double t, x; } QUE;
QUE que[QMAX]; int qsize;

#define PARENT(i) ((i)>>1)
#define LEFT(i)   ((i)<<1)
#define RIGHT(i)  (((i)<<1)+1)

void min_heapify(int i)
{
	int l, r, min;
	QUE qt;

	l = LEFT(i), r = RIGHT(i);
	if (l < qsize && que[l].t < que[i].t) min = l; else min = i;
	if (r < qsize && que[r].t < que[min].t) min = r;
	if (min != i) {
		qt = que[i], que[i] = que[min], que[min] = qt;
		min_heapify(min);
	}
}

void deq()
{
	que[0] = que[--qsize];
	min_heapify(0);
}

void enq(short s, double t, double x)
{
	int i, min;
	QUE qt;

	i = qsize++;
	que[i].s = s, que[i].t = t, que[i].x = x;
	while (i > 0 && que[min = PARENT(i)].t > que[i].t) {
		qt = que[i], que[i] = que[min], que[min] = qt;
		i = min;
	}
}

#define N			100
#define EPS			1e-8
#define EQ(a,b)		(fabs((a)-(b))<EPS)

typedef struct { double x, y; } PP;
typedef struct { PP s, e; } SEG;

PP p[21];
PP po0[4] = {{0,0},{4,0},{4,4},{0,4}};
PP po[2][200];

PP  tbl[N]; int sz;
short hi[N], lim[N], *to[N];
char mk[N];

#define PPeQ(a,b)	(EQ(a.x,b.x)&&EQ(a.y,b.y))
int dcmp(double x) { if (fabs(x) < EPS) return 0; return x <= 0 ? -1 : 1; }
PP vsub(PP p1, PP p2) { PP r; r.x = p1.x - p2.x, r.y = p1.y - p2.y; return r; }
double cross(PP a, PP b) { return a.x * b.y - a.y * b.x; }
double vabs(PP a) { return hypot(a.x, a.y); }

// ２線分間の交点
PP crossPointS2P(SEG a, PP bs, PP be) { double a1, a2; PP r;
	a1 = cross(vsub(be, bs), vsub(a.s, bs));
	a2 = cross(vsub(be, bs), vsub(a.e, bs));
	r.x = (a.s.x*a2 - a.e.x*a1) / (a2-a1);
	r.y = (a.s.y*a2 - a.e.y*a1) / (a2-a1);
	return r;
}

// 垂直二等分線
void bisector(SEG *u, PP a, PP b)
{
	double ax = (a.x + b.x)/2;
	double ay = (a.y + b.y)/2;
	u->s.x = ax, u->s.y = ay;
	if (fabs(a.y - b.y) <= EPS) u->e.x = ax, u->e.y = ay + (b.x-a.x)*100;
	else u->e.x = ax-(b.y-a.y)*100, u->e.y = (ax - u->e.x)*(b.x - a.x)/(b.y - a.y) + ay;
}

// 凸包を直線で切断して左側をpo[]に残す
int convex_cut(SEG u, int n, PP *p, PP *po)		// p --> po
{
	int i, d1, d2, top = 0;
    for (i = 0; i < n; i++) {
        d1 = dcmp(cross(vsub(u.e, u.s), vsub(p[i],   u.s)));
        d2 = dcmp(cross(vsub(u.e, u.s), vsub(p[i+1], u.s)));
        if (d1 >= 0) po[top++] = p[i];
        if (d1*d2 < 0) po[top++] = crossPointS2P(u, p[i], p[i+1]);
    }
	po[top] = po[0];
    return top;
}

void pushBack(int a, int b)
{
	int k;

	if (EQ(tbl[a].y, 0) && EQ(tbl[b].y, 0)) return;
	if (EQ(tbl[a].y, 4) && EQ(tbl[b].y, 4)) return;

	if (lim[a] == 0) {
		lim[a] = 2, hi[a] = 0;
		to[a] = malloc(sizeof(short) *lim[a]);
	} else if (hi[a] == lim[a]) {
		lim[a] <<= 1;
		to[a] = realloc(to[a], sizeof(short) *lim[a]);
	}

	for (k = 0; k < hi[a]; k++) if (to[a][k] == b) return;
	to[a][hi[a]++] = b;
}

double dijkstra()
{
	int i, s, e;
	double t, x;

	memset(mk, 0, sizeof(mk));
	qsize = 0;
	for (i = 0; i < sz; i++) {
		if (EQ(tbl[i].x, 0)) enq(i, 0, 0), mk[i] = 1;
	}

	while (qsize) {
		s = que[0].s, t = que[0].t, x = que[0].x, deq();
		if (EQ(x, 4)) return t;

		for (i = 0; i < hi[s]; i++) {
			e = to[s][i];
			if (mk[e]) continue;
			mk[e] = 1, enq(e, t+vabs(vsub(tbl[s],tbl[e])), tbl[e].x);
		}
	}
	return -1;
}

int main()
{
	int n, i, j, k, k1, k2, a, b, c;
	SEG u;
	double ans;

	while (scanf("%d", &n) && n) {
		for (i = 0; i < n; i++) scanf("%lf%lf", &p[i].x, &p[i].y);
		if (n == 1) { puts("impossible"); continue; }

		sz = 0, memset(hi, 0, sizeof(hi)), memset(lim, 0, sizeof(lim));
		memset(po, 0, sizeof(po));
		for (i = 0; i < n; i++) {
			memcpy(po[0], po0, sizeof(po0));
			k = 4, k1 = 0, k2 = 1;
			for (j = 0; j < n; j++) {
				if (j == i) continue;
				bisector(&u, p[i], p[j]);
				k = convex_cut(u, k, po[k1], po[k2]);
				k1 = k2, k2 = !k2;
			}
			if (k <= 1) continue;
			if (k == 2) {
				tbl[a=sz++] = po[k1][0], tbl[b=sz++] = po[k1][1];
				pushBack(a, b), pushBack(b, a);
			} else {			// k >= 3
				j = sz;			// j as memo
				for (b = 0; b < k; b++) tbl[sz++] = po[k1][b];
				a = k-1, c = 1; for (b = 0; b < k; b++) {
					pushBack(j+b, j+a), pushBack(j+b, j+c);
					if (++a == k) a = 0;
					if (++c == k) c = 0;
				}
			}
		}
		for (i = 0; i < sz; i++) for (j = i+1; j < sz; j++) {
			if (PPeQ(tbl[i], tbl[j])) pushBack(i, j), pushBack(j, i);
		}

		if ((ans = dijkstra()) < 0) puts("impossible");
		else printf("%.12lf\n", ans);

		for (i = 0; i < sz; i++) if (lim[i]) free(to[i]);
	}
	return 0;
}
