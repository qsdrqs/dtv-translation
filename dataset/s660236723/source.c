#include<stdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

long long int gcd(long long int a, long long int b) {
	long long int tmp;
	long long int r = 1;
	if (b > a) {
		tmp = a;
		a = b;
		b = tmp;
	}
	r = a % b;
	while (r != 0) {


		a = b;
		b = r;
		r = a % b;

	}
	return b;
}
int main() {
	long long int t, a, b, c, d, GCD, memo;
	scanf("%lld", &t);
	for (int i = 1; i <= t; i++) {
		scanf("%lld%lld%lld%lld", &a, &b, &c, &d);
		if (b > d||a%b>c) { printf("No\n"); continue; }
		if (a < b) {
			printf("No\n"); continue;
		}
		if (a <= c) {
			if (a - b < 0) {
				printf("No\n"); continue;
			}
			else {
				printf("Yes\n"); continue;
			}
		}
		GCD = gcd(b, d);
		memo = (a%b) +((c-(a%b))/GCD)*GCD +GCD- b;

		if (memo < 0) {
			printf("No\n"); continue;
		}
		else {
			printf("Yes\n"); continue;
		}
	}
}