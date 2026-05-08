// AOJ 2033 Rock Man
// 2018.3.16 bal4u

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

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

int in()  // 非負整数の入力
{
	int n = 0, c = gc();
	while (!isdigit(c)) c = gc();
	do n = 10 * n + (c & 0xf), c = gc(); while (isdigit(c));
	return n;
}

void ins(char *s)  // 文字列の入力　スペース以下の文字で入力終了
{
	char c = gc();
	while (isspace(c)) c = gc();
	*s++ = c;
	do *s = gc(); while (isalpha(*s++));
	*(s - 1) = 0;
}

// 文字列のハッシュ関数
#define HASHSIZ 9973
typedef struct { char *s; int id; } HASH;
HASH hash[HASHSIZ + 2], *hashend = hash + HASHSIZ;

int insert(char *s, int id)
{
	unsigned long long i;
	int j;
	char *p;
	HASH *tp;

	i = 0, p = s;
	for (j = 0; *p && j < 12; j++) i = (i << 5) + (*p++ + 1 - 'a');
	tp = hash + (int)(i % HASHSIZ);
	while (tp->s != NULL) {
		if (!strcmp(tp->s, s)) return tp->id;
		if (++tp == hashend) tp = hash;
	}
	tp->s = s, tp->id = id;
	return -1;
}

#define MAX_V 1005
int  V;    // 頂点数
int  *to[MAX_V], hi[MAX_V];
int  *r_to[MAX_V], r_hi[MAX_V];
int  vs[MAX_V], vsz;
char used[MAX_V];
int  cmp[MAX_V];    // 属する強連結成分のトポロジカル順序

void add_edge(int _from, int _to)
{
	to[_from][hi[_from]++] = _to;
	r_to[_to][r_hi[_to]++] = _from;
}

void dfs(int v)
{
	int i;
	used[v] = 1;
	for (i = 0; i < hi[v]; i++) {
		if (!used[to[v][i]]) dfs(to[v][i]);
	}
	vs[vsz++] = v;
}

void rdfs(int v, int k)
{
	int i;
	used[v] = 1;
	cmp[v] = k;
	for (i = 0; i < r_hi[v]; i++) {
		if (!used[r_to[v][i]]) rdfs(r_to[v][i], k);
	}
}

// 強連結成分への分解
int scc()
{
	int v, i, k;
	memset(used, 0, V);
	vsz = 0;
	for (v = 0; v < V; v++) if (!used[v]) dfs(v);
	memset(used, 0, V);
	k = 0;
	for (i = vsz - 1; i >= 0; i--) {
		if (!used[vs[i]]) rdfs(vs[i], k++);
	}
	return k;		// 得られた強連結成分の数
}

typedef struct { int id, sup, day1, day2, diff; } T;
T tbl[1005];

char name[1002][35]; int sz;
char f[1002];    // 各強連結成分内のグループの個数。 1 か 2以上か。

int sort_cmp(const void *a, const void *b) { return ((T *)a)->diff - ((T *)b)->diff; }

int main()
{
	int k, i, ans;

	while (V = in()) {
		memset(hash, 0, sizeof(hash));
		sz = 0;  for (i = 0; i < V; i++) {
			ins(name[sz]);
			if ((k = insert(name[sz], sz)) < 0) k = sz++;
			tbl[i].id = k;
			tbl[i].day1 = in();
			ins(name[sz]);
			if ((k = insert(name[sz], sz)) < 0) k = sz++;
			tbl[i].sup = k;
			tbl[i].day2 = in();
			tbl[i].diff = tbl[i].day1 - tbl[i].day2;
		}
		qsort(tbl, V, sizeof(T), sort_cmp);

		memset(hi, 0, sizeof(hi));
		memset(r_hi, 0, sizeof(r_hi));
		for (i = 0; i < V; i++) {
			hi[tbl[i].sup]++;
			r_hi[tbl[i].id]++;
		}

		for (i = 0; i < V; i++) {
			if (hi[i])   to[i] = malloc(hi[i] * sizeof(int));
			if (r_hi[i]) r_to[i] = malloc(r_hi[i] * sizeof(int));
		}
		memset(hi, 0, sizeof(hi));
		memset(r_hi, 0, sizeof(r_hi));
		for (i = 0; i < V; i++) {
			if (tbl[i].sup != tbl[i].id) add_edge(tbl[i].sup, tbl[i].id);
		}

		scc();		//強連結成分への分解

		memset(f, 0, sizeof(f));
		for (i = 0; i < V; i++) {
			k = cmp[tbl[i].id];
			if (f[k] < 2) f[k]++;
		}

		ans = 0;
		for (i = 0; i < V; i++) {
			if (r_hi[tbl[i].id] == 0) ans += tbl[i].day1;
			else {
				k = cmp[tbl[i].id];
				if (f[k] > 1) ans += tbl[i].day1, f[k] = -1;
				else ans += tbl[i].day2;
			}
		}
		printf("%d\n", ans);

		for (i = 0; i < V; i++) {
			if (hi[i])   free(to[i]);
			if (r_hi[i]) free(r_to[i]);
		}
	}
	return 0;
}
