// AOJ 2437 DNA
// 2018.4.7 bal4u

#include <stdio.h>
#include <string.h>

// 文字列のハッシュ関数
#define HASHSIZ 503
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { char *s; int id; } HASH;
HASH hash[HASHSIZ+2], *hashend = hash+HASHSIZ;

int insert(char *s, int id)
{
	unsigned long long i;
	char *p;
	HASH *tp;

	i = 0, p = s; while (*p) i = (i<<5) + *p++;
	tp = hash + (int)(i % HASHSIZ);
	while (tp->s != NULL) {
		if (!strcmp(tp->s, s)) return tp->id;
		if (++tp == hashend) tp = hash;
	}
	tp->s = s, tp->id = id;
	return -1;
}

char buf[300], *p;
int in()
{
	int n = 0;
	while (*p >= '0') n = 10 * n + (*p++ & 0xf);
	p++;
	return n;
}

#define M 1000000007

int  na, nt, ng, nc, sum;
int  sz;
int  rule[52][12];
int  dp[202][52][52][52];
char text[52][300];
char tr['Z'];
int  token[250], uniq[250];

int together(int id)
{
	int i, j;

	for (i = 0; j = rule[id][i]; i++) {
		if (j > 0) { if (together(j)) return 1; }
		else {
			token[sz] = -j;
			if (++sz > sum) return 1;
		}
	}
	return 0;
}

int main()
{
	int m, i, j, k, l, b, a, t, g, c, la, lt, lg;
	char *q;

	tr['A'] = 1, tr['T'] = 2, tr['G'] = 4, tr['C'] = 8;
	fgets(p = buf, 20, stdin);
	na = in(), nt = in(), ng = in(), nc = in();
	sum = na + nt + ng + nc;
	fgets(p = buf, 10, stdin), m = in();
	sz = 0;
	for (i = 0; i < m; i++) {
		fgets(p = text[i], 300, stdin);
		q = p; while (*p != ':') p++; *p = 0, p += 2;
		j = insert(q, sz);
		if (j < 0) j = sz++;
		k = 0;
		while (*p >= ' ') {
			q = p; while (*p > ' ') p++; *p++ = 0;
			if (*q != '[') {
				l = insert(q, sz);
				if (l < 0) l = sz++;
				rule[j][k++] = l;
			}
			else {
				b = 0;
				while (*++q != ']') b |= tr[*q];
				rule[j][k++] = -b;
			}
		}
	}
#if 0
	printf("m %d, sz %d, sum %d\n", m, sz, sum);
	for (i = 0; i < sz; i++) {
		printf("[%d] --> ", i);
		for (j = 0; rule[i][j]; j++) printf("%d ", rule[i][j]);
		printf("\n");
	}
#endif
	sz = 0;
	if (together(0) || sz != sum) goto zero;

	j = 0; for (i = 0; i < sz; i++) {
		if ((b = token[i]) == 1) na--;
		else if (b == 2) nt--;
		else if (b == 4) ng--;
		else if (b == 8) nc--;
		else uniq[j++] = token[i];
	}
	sz = j;
	if (na < 0 || nt < 0 || ng < 0 || nc < 0) goto zero;

#if 0
	printf("sz %d\n", sz);
	for (i = 0; i < sz; i++) printf("[%d] %d\n", i, token[i]);
#endif

	dp[0][0][0][0] = 1;
	for (i = 0; i < sz; i++) {
		b = uniq[i];
		la = na; if (i < la) la = i;
		for (a = 0; a <= la; a++) {
			lt = nt; if (i - a < lt) lt = i - a;
			for (t = 0; t <= lt; t++) {
				lg = ng;; if (i - a - t < lg) lg = i - a - t;
				for (g = 0; g <= lg; g++) {
					c = i - (a + t + g);
					if (c < 0 || c > nc) continue;
					if (b & 1) {
						dp[i + 1][a + 1][t][g] += dp[i][a][t][g];
						if (dp[i + 1][a + 1][t][g] >= M) dp[i + 1][a + 1][t][g] -= M;
					}
					if (b & 2) {
						dp[i + 1][a][t + 1][g] += dp[i][a][t][g];
						if (dp[i + 1][a][t + 1][g] >= M) dp[i + 1][a][t + 1][g] -= M;
					}
					if (b & 4) {
						dp[i + 1][a][t][g + 1] += dp[i][a][t][g];
						if (dp[i + 1][a][t][g + 1] >= M) dp[i + 1][a][t][g + 1] -= M;
					}
					if (b & 8) {
						dp[i + 1][a][t][g] += dp[i][a][t][g];
						if (dp[i + 1][a][t][g] >= M) dp[i + 1][a][t][g] -= M;
					}
				}
			}
		}
	}
	printf("%d\n", dp[sz][na][nt][ng]);
	return 0;
zero: puts("0");
	return 0;
}
