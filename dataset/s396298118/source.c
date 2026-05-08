// AOJ 1520 Light Source
// 2018.3.20 bal4u

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// 高速数値入出力
#if 1
#define gc() getchar_unlocked()
#else
#define gc() getchar()
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int in()   // 整数の入力（負数に対応）
{
	int n = 0, c = gc();
	if (c == '-') {
		c = gc();
		do n = 10 * n + (c & 0xf), c = gc(); while (c >= '0');
		return -n;
	}
	do n = 10 * n + (c & 0xf), c = gc(); while (c >= '0');
	return n;
}


// トポロジーソート
#define MAX 105
int hi[MAX], to[MAX][MAX];   // トポロジーソートのための有向グラフ構造
int res[MAX];                // トポロジーソートの結果。後ろのほうが指されたもの。
void topoSort(int V)
{
	int i, j, k, sz;
	static int q[MAX], top, end;
	static int count[MAX];

//	memset(count, 0, sizeof(count));
	for (i = 0; i < V; i++) for (j = 0; j < hi[i]; j++) count[to[i][j]]++;
	top = end = 0;
	for (i = 0; i < V; i++) if (!count[i]) q[end++] = i;
	sz = 0;  while (top < end) {
		res[sz++] = i = q[top++];
		for (j = 0; j < hi[i]; j++) {
			k = to[i][j];
			if (--count[k] == 0) q[end++] = k;
		}
	}
}


// 平面幾何
typedef struct { double x, y; } PP;    // 点
typedef struct { PP s, e; } SEG, LINE;    // 線分、直線
typedef struct { double x, y, r; } C;   // 円

#define INF			1e8
#define EPS			1e-8
#define EQ(a,b)		(fabs((a)-(b))<EPS)
#define DEG2RAD(a)  ((a)*0.01745329251994329576923690768489)
#define PI2         6.283185307179586476925286766559  // pi*2

PP vset(double x, double y) { PP r; r.x = x, r.y = y; return r; }
PP vsub(PP p1, PP p2) { PP r; r.x = p1.x - p2.x, r.y = p1.y - p2.y; return r; }
double vabs(PP a) { return hypot(a.x, a.y); }
double dist(PP p1, PP p2) { return hypot(p1.x - p2.x, p1.y - p2.y); }
double angle(double a) { if (a <= 0) a += PI2; return a; }

// 円と円の交点。交点が２つ、または１つか、ゼロ
int intersectCC(C c1, C c2, PP *p1, PP *p2)
{
	double x1 = c1.x, y1 = c1.y, r1 = c1.r;
	double x2 = c2.x, y2 = c2.y, r2 = c2.r;
	double d = dist(vset(x1, y1), vset(x2, y2));
	double w, n, x, y, p, q;
	double u, v;

	u = r1 + r2, v = fabs(r1 - r2);

	if ((fabs(d - u) > EPS && d >= u) || fabs(v - d) > EPS && d <= v) return 0;
	w = ((r1*r1 - r2 * r2) / d + d) / 2;
	n = sqrt(r1*r1 - w * w);
	x = x1 + (x2 - x1)*w / d;
	y = y1 + (y2 - y1)*w / d;
	p = (y2 - y1)*n / d;
	q = (x2 - x1)*n / d;

	p1->x = x + p, p2->x = x - p;
	p1->y = y - q; p2->y = y + q;
	if (fabs(d - u) <= EPS) return 1;
	if (d == r1 + r2) return 1;
	return 2;
}

// 光源 dst が光源 c の照射範囲にあるか
int contained(C c, int a, double b, double d, C dst)
{
	PP p1, p2;
	double t, bb, dd;

	t = dist(vset(c.x, c.y), vset(dst.x, dst.y)) + dst.r;
	if (!EQ(a, t) && a <= t) return 0;
	if (intersectCC(c, dst, &p1, &p2) > 1) return 0;

	if ((t = dist(vset(dst.x, dst.y), vset(c.x, c.y))) < dst.r) return 0;
	dd = asin(dst.r / t);
	bb = angle(atan2(dst.y - c.y, dst.x - c.x)) - dd;
	dd *= 2.0;
	if (bb < 0) bb += PI2;
	if (b < 0) b += PI2;

	if ((EQ(b,bb) || b <= bb) && (EQ(bb+dd,b+d) || bb+dd <= b+d)) return 1;
	if (b > bb) {
		if (b <= bb + PI2 && bb + dd + PI2 <= b + d) return 1;
	}
	return 0;
}


// 本問題関連
typedef struct { C c; int a; double b, d; int p; } T;    // 光源のパラメータ
T t[105]; int N;
int d0, a0, p0;  // 最初の光源
int val[105];

int main()
{
	int i, j, k, id, ans;
	double a;
	C org;

	// 入力処理
	N = in(), d0 = in(), a0 = in(), p0 = in();
	org.x = org.y = org.r = 0;
	k = 0;  for (i = 0; i < N; i++) {
		t[k].c.x = in(), t[k].c.y = in(), t[k].c.r = in();
		t[k].d = in(), t[k].a = in(), t[k].b = in(), t[k].p = in();
		t[k].b = angle(t[k].b-t[k].d*0.5); 
		if (t[k].p > 0) k++;
	}
	t[k].c.x = in(), t[k].c.y = in(), t[k].c.r = in(), t[k].p = (int)INF;
	N = k;

	// 光源間の依存関係を調べる
	for (i = 0; i < N; i++) for (j = 0; j <= N; j++) if (i != j) {
		if (contained(t[i].c, t[i].a, DEG2RAD(t[i].b), DEG2RAD(t[i].d), t[j].c)) {
			to[i][hi[i]++] = j;     // 光源 j が光源 i の照射範囲にある
		}
	}
	topoSort(N + 1);

	// 全数検索
	ans = 0;
	for (i = 0; i <= N; i++) {
		memset(val, 0, sizeof(val));
		a = angle(atan2(t[i].c.y, t[i].c.x) -
			asin(t[i].c.r / vabs(vset(t[i].c.x, t[i].c.y))));
		for (j = 0; j <= N; j++) {
			if (contained(org, a0, a, DEG2RAD(d0), t[j].c)) {
				val[j] += p0;
			}
		}
		for (j = 0; j <= N; j++) {
			id = res[j];
			if (val[id] == 0) continue;
			if (val[id] > t[id].p) val[id] = t[id].p;
			for (k = 0; k < hi[id]; k++) val[to[id][k]] += val[id];
		}
		if (val[N] > ans) ans = val[N];
	}
	printf("%d\n", ans);
	return 0;
}
