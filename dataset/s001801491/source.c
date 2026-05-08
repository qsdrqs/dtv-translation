#include <stdio.h>
#include <stdlib.h>

#define MOD 1000000007
#define MAX 100000
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int p2[MAX+5];
int f[MAX + 5];

int main()
{
	int i, t;
	int N, M;

	p2[0] = 1;
	for (i = 1; i <= MAX; i++) p2[i] = (p2[i - 1] << 1) % MOD;

	scanf("%d%d", &N, &M);

	f[M] = 1;

	for (i = M + 1; i < N && i <= 2 * M; i++) {
		f[i] = ((f[i - 1] << 1) % MOD + p2[i - M - 1]) % MOD;
	}

	for (; i <= N; i++) {
		t = p2[i - M - 1] - f[i - M - 1];
		if (t < 0) t += MOD;
		f[i] = ((f[i - 1] << 1) % MOD + t) % MOD;
	}
	printf("%d\n", f[N]);
	return 0;
}
