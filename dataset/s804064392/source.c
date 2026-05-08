// AOJ DPL_5_I: Balls and Boxes 9
// n 個の区別できるボールを k 個の区別できない箱に入れる
// とき、可能な入れ方の総数を求めてください。
// ただし、
//    どのボールも、必ずいずれかの箱に入れる。
//    どの箱にも、1つ以上のボールを入れる。
// 答えは第2種スターリング数 stirling2(n, k)
// 2019.3.11 bal4u

#include <stdio.h>
#include <stdlib.h>

#define MOD 1000000007
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int tbl[1001][1001];

int stirling2(int n, int k)
{
	int ans;

	if (k == 0) return 0;
	if (tbl[n][k]) return tbl[n][k];
	if (k == 1 || k == n) ans = 1;
	else ans = (((long long)k * stirling2(n - 1, k)) % MOD)
		+ stirling2(n - 1, k - 1);
	return tbl[n][k] = ans % MOD;
}

int main()
{
	int n, k;

	scanf("%d%d", &n, &k);
	if (n < k) puts("0");
	else printf("%d\n", stirling2(n, k));
	return 0;
}
