#include <stdio.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int N;
int L[64];

int ruiseki[64];

int sedai;
int saisyou;
int target;
int visited[64];

int dekiru(int idx) {
	int i;
	if (idx >= N) return 1;
	if (visited[idx] >= sedai) return visited[idx] & 1;
	for (i = idx + 1; i <= N; i++) {
		int len = ruiseki[i] - ruiseki[idx];
		if (len < saisyou) continue;
		if (saisyou + target < len) break;
		if (dekiru(i)) {
			visited[idx] = sedai + 1;
			return 1;
		}
	}
	visited[idx] = sedai;
	return 0;
}

int dekirukana(void) {
	int i, j, k;
	/* doko wo saisyou ni suru ka tansaku */
	for (i = 0; i < N; i++) {
		for (j = i + 1; j <= N; j++) {
			saisyou = ruiseki[j] - ruiseki[i];
			/* toriaezu kiru */
			for (k = 1; k < N; k++) {
				int len = ruiseki[k] - ruiseki[0];
				if (len < saisyou) continue;
				if (saisyou + target < len) break;
				sedai += 2;
				if (dekiru(k)) return 1;
			}
		}
	}
	return 0;
}

int main(void) {
	int i;
	if (scanf("%d", &N) != 1) return 1;
	for (i = 1; i <= N; i++) {
		if (scanf("%d", &L[i]) != 1) return 1;
		ruiseki[i] = ruiseki[i - 1] + L[i];
	}
	target = 0;
	if (dekirukana()) {
		puts("0");
	} else {
		int ng = 0, ok = 1000;
		while (ng + 1 < ok) {
			int mid = ng + (ok - ng) / 2;
			target = mid;
			if (dekirukana()) ok = mid; else ng = mid;
		}
		printf("%d\n", ok);
	}
	return 0;
}

