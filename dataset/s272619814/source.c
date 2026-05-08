// AtCoder ABC138: D - Ki
// 2019.8.26 bal4u

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if 1
#define gc() getchar_unlocked()
#define pc(c) putchar_unlocked(c)
#else
#define gc() getchar()
#define pc(c) putchar(c)
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

int in() {   // 非負整数の入力
	int n = 0, c = gc();
	do n = 10 * n + (c & 0xf); while ((c = gc()) >= '0');
	return n;
}

void out(int n) { // 非負整数の表示（出力）
	int i; char b[30];

	if (!n) pc('0');
	else {
		i = 0; while (n) b[i++] = n % 10 + '0', n /= 10;
		while (i--) pc(b[i]);
	}
}

#define MAX 200005
int hi[MAX], *to[MAX], x[MAX]; int N;

void calc(int node, int par, int v) {
	int i, a;
	
	x[node] += v;
	for (i = 0; i < hi[node]; i++) {
		a = to[node][i];
		if (a != par) calc(a, node, x[node]);
	}
}
		
int main()
{
	int i, a, b, N, Q;
	int *memo, sz;
	
	N = in(), Q = in();
	
	memo = malloc(N*sizeof(int)*2);
	sz = 0; for (i = 1; i < N; i++) {
		a = in(), b = in();
		memo[sz++] = a, memo[sz++] = b;
		hi[a]++, hi[b]++;
	}
	
	for (i = 1; i <= N; i++) if (hi[i]) to[i] = malloc(hi[i]*sizeof(int));
	memset(hi, 0, sizeof(hi));
	i = 0; while (i < sz) {
		a = memo[i++], b = memo[i++];
		to[a][hi[a]++] = b, to[b][hi[b]++] = a;
	}
	free(memo);
	
	while (Q--) a = in(), x[a] += in();
	
	calc(1, 0, 0);
	out(x[1]); for (i = 2; i <= N; i++) pc(' '), out(x[i]);
	pc('\n');
	return 0;
}
