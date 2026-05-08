#include <stdio.h>
#include <stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int gcd(int a, int b)
{
	if (a > b) {
		a ^= b;
		b ^= a;
		a ^= b;
	}
	if (a == 0) return b;
	else return gcd(b % a, a);
}

long long solve(int W, int H, int K)
{
	long long i, j, k, l[2], r[2], ans = 0;
	for (k = 1; k <= (H - 1) / 2; k++) {
		l[0] = (K * 2 - k * (W + 1)) / (H - k);
		r[0] = ((K + H) * 2 - k + H - k - 1) / (H - k);
		if (l[0] < 1) l[0] = 1;
		else if (l[0] >= W) {
			ans += (long long)(W - 1) * (W - 1);
			continue;
		}
		if (r[0] <= 1) break;
		else if (r[0] > W) r[0] = W;
		ans += (long long)(l[0] - 1) * (W - 1);
		
		for (i = l[0]; i < r[0]; i++) {
			l[1] = (K * 2 - (H - k) * i + k - 1) / k;
			r[1] = ((K + H) * 2 - (H - k) * i + k - 1) / k;
			if (l[1] < 1) l[1] = 1;
			else if (l[1] >= W) {
				ans += W - 1;
				continue;
			}
			if (r[1] <= 1) break;
			else if (r[1] > W) r[1] = W;
			ans += l[1] - 1;
			for (j = l[1]; j < r[1]; j++) if (j * k + i * (H - k) - gcd(i, k) - gcd(j, H - k) - gcd(abs(i - j), H) < K * 2) ans++;
		}
	}
	for (k = 1; k <= (W - 1) / 2; k++) {
		l[0] = (K * 2 - k * (H + 1)) / (W - k);
		r[0] = ((K + W) * 2 - k + W - k - 1) / (W - k);
		if (l[0] < 1) l[0] = 1;
		else if (l[0] >= H) {
			ans += (long long)(H - 1) * (H - 1);
			continue;
		}
		if (r[0] <= 1) break;
		else if (r[0] > H) r[0] = H;
		ans += (long long)(l[0] - 1) * (H - 1);
		
		for (i = l[0]; i < r[0]; i++) {
			l[1] = (K * 2 - (W - k) * i + k - 1) / k;
			r[1] = ((K + W) * 2 - (W - k) * i + k - 1) / k;
			if (l[1] < 1) l[1] = 1;
			else if (l[1] >= H) {
				ans += H - 1;
				continue;
			}
			if (r[1] <= 1) break;
			else if (r[1] > H) r[1] = H;
			ans += l[1] - 1;
			for (j = l[1]; j < r[1]; j++) if (j * k + i * (W - k) - gcd(i, k) - gcd(j, W - k) - gcd(abs(i - j), W) < K * 2) ans++;
		}
	}
	ans *= 2;
	
	if (H % 2 == 0) {
		k = H / 2;
		for (i = 1; i < W; i++) {
			l[1] = (K * 2 - (H - k) * i + k - 1) / k;
			r[1] = ((K + H) * 2 - (H - k) * i + k - 1) / k;
			if (l[1] < 1) l[1] = 1;
			else if (l[1] >= W) {
				ans += W - 1;
				continue;
			}
			if (r[1] <= 1) break;
			else if (r[1] > W) r[1] = W;
			ans += l[1] - 1;
			for (j = l[1]; j < r[1]; j++) if (j * k + i * (H - k) - gcd(i, k) - gcd(j, H - k) - gcd(abs(i - j), H) < K * 2) ans++;
		}
	}
	if (W % 2 == 0) {
		k = W / 2;
		for (i = 1; i < H; i++) {
			l[1] = (K * 2 - (W - k) * i + k - 1) / k;
			r[1] = ((K + W) * 2 - (W - k) * i + k - 1) / k;
			if (l[1] < 1) l[1] = 1;
			else if (l[1] >= H) {
				ans += H - 1;
				continue;
			}
			if (r[1] <= 1) break;
			else if (r[1] > H) r[1] = H;
			ans += l[1] - 1;
			for (j = l[1]; j < r[1]; j++) if (j * k + i * (W - k) - gcd(i, k) - gcd(j, W - k) - gcd(abs(i - j), W) < K * 2) ans++;
		}
	}
	
	return ans * 2;
}

int main()
{
	int W, H, K;
	scanf("%d %d %d", &W, &H, &K);
	printf("%lld\n", solve(W, H, K));
	fflush(stdout);
	return 0;
}