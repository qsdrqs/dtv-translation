// AOJ 2328 Mobile Network
// 2018.3.13 bal4u

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#define CZ       0
#define CINF     1

#define VMAX 53
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { short to, cap, rev; } EDGE;
EDGE edge[VMAX][VMAX]; short hi[VMAX];
int V;				// 頂点数
short level[VMAX], iter[VMAX];
int queue[2*VMAX], qtop;

typedef struct { short w, c[55]; } CAP;
CAP cap[15000]; int cid;

char buf[600], *p;
int in()
{
	int n = 0;
	while (isdigit(*p)) n = 10*n + (*p++ & 0xf); p++;
	return n;
}

int cap_new() { int id = cid++;	cap[id].w = 1, cap[id].c[0] = 0; return id; }
void cap_set(int id1, int id2) { memcpy(cap+id1, cap+id2, sizeof(CAP)); }
// int cap_zero(int id) { return cap[id].c[cap[id].w-1]; }
#define cap_zero(id)         (cap[id].c[cap[id].w-1])

void cap_norm(int id)
{
	int w = cap[id].w - 1;
	while (w > 0 && cap[id].c[w] == 0) w--;
	cap[id].w = w + 1;
}

int cap_cmp(int id1, int id2)
{
	int w1 = cap[id1].w-1, w2 = cap[id2].w-1;
	if (w1 > w2) return  cap[id1].c[w1];
	if (w2 > w1) return  -cap[id2].c[w2];
	while (w1 > 0 && cap[id1].c[w1] == cap[id2].c[w1]) w1--;
	return cap[id1].c[w1] - cap[id2].c[w1];
}

void cap_add(int id1, int id2)
{
	int i, w1 = cap[id1].w, w2 = cap[id2].w;
	if (w1 > w2) for (i = 0; i < w2; i++) cap[id1].c[i] += cap[id2].c[i];
	else {
		for (i = 0; i < w1; i++) cap[id1].c[i] += cap[id2].c[i];
		for (     ; i < w2; i++) cap[id1].c[i]  = cap[id2].c[i];
		cap[id1].w = cap[id2].w;
//		cap_norm(id1);
	}
}

void cap_sub(int id1, int id2)
{
	int i, w1 = cap[id1].w, w2 = cap[id2].w;
	if (w1 > w2) for (i = 0; i < w2; i++) cap[id1].c[i] -= cap[id2].c[i];
	else {
		for (i = 0; i < w1; i++) cap[id1].c[i] -= cap[id2].c[i];
		for (     ; i < w2; i++) cap[id1].c[i] = -cap[id2].c[i];
		cap[id1].w = cap[id2].w;
		cap_norm(id1);
	}
}

void str2cap(int id)
{
	int c, e, w = 0;

	while (*p > ' ') {
		if (*p == '+') p++;
		c = 1; if (isdigit(*p)) c = in(), p--;
		e = 0; if (*p == 'x') {
			p++; e = 1;
			if (*p == '^') { p++; if (isdigit(*p)) e = in(), p--; }
		}
		cap[id].c[e] = c;
		if (e > w) w = e;
	}
	cap[id].w = w+1;
}

void coutcap(int id)
{
	int f = 0, i;

	for (i = cap[id].w-1; i > 0; i--) {
		if (cap[id].c[i] == 0) continue;
		if (f) putchar('+');
		if (cap[id].c[i] != 1) printf("%d", cap[id].c[i]);
		f = 1, putchar('x');
		if (i > 1) printf("^%d", i);
	}
	if (!f) printf("%d", cap[id].c[0]);
	else if (cap[id].c[0]) printf("+%d", cap[id].c[0]);
	putchar('\n');
}

void add_edge(int from, int to, int id)
{
	int f, t, c;
	EDGE *e;

	f = hi[from]++, t = hi[to]++;
	e = &edge[from][f], e->to = to, e->cap = id, e->rev = t;
	c = cap_new(), cap_set(c, id);
	e = &edge[to][t], e->to = from, e->cap = c, e->rev = f;
}

void bfs(int s)
{
	int i, v;
	EDGE *e;
	
	memset(level, -1, V << 1);
	level[s] = 0;
	queue[0] = s, qtop =1;
	while (qtop) {
		v = queue[--qtop];
		for (i = 0; i < hi[v]; i++) {
			e = &edge[v][i];
			if (cap_zero(e->cap) > 0 && level[e->to] < 0) {
				level[e->to] = level[v] + 1;
				queue[qtop++] = e->to;
			}
		}
	}
}
 
int dfs(int v, int t, int f)
{
	int  d, ff;
	EDGE *e;
	short *i;
	
	if (v == t) return f;
	ff = cap_new(), cap_set(ff, f);
	d = cap_new();
	for (i = &iter[v]; *i < hi[v]; (*i)++) {
		e = &edge[v][*i];
		if (cap_zero(e->cap) > 0 && level[v] < level[e->to]) {
			if (cap_cmp(ff, e->cap) <= 0) cap_set(d, dfs(e->to, t, ff));
			else                          cap_set(d, dfs(e->to, t, e->cap));
			if (cap_zero(d) > 0) {
				cap_sub(e->cap, d);
				cap_add(edge[e->to][e->rev].cap, d);
				return d;
			}
		}
	}
	return CZ;
}
 
int maxFlow(int s, int t)
{
	int f =	cap_new();
	int flow = cap_new();

	while (1) {
		bfs(s);
		if (level[t] < 0) break;
		memset(iter, 0, V << 1);
		while (1) {
			cap_set(f, dfs(s, t, CINF));
			if (cap_zero(f) <= 0) break;
			cap_add(flow, f);
		}
	}
	return flow;
}

int main()
{
	int N, M, i, u, v;

	while (fgets(p=buf, 10, stdin) && *p != '0') {
		memset(cap, 0, sizeof(cap));
		cap[CZ].w = 1, cap[CZ].c[0] = 0;
		cap[CINF].w = 53, cap[CINF].c[52] = 1;
		cid = 2;

		N = in(), M = in();
		V = N; memset(hi, 0, V << 1);

		for (i = 0; i < M; i++) {
			fgets(p=buf, 600, stdin);
			u = in()-1, v = in()-1, str2cap(cid++);
			add_edge(u, v, cid-1);
		}
		coutcap(maxFlow(0, N-1));
	}
	return 0;
}
