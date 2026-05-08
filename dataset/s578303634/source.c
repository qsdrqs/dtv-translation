#include <stdio.h>
#include <inttypes.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int32_t N;
int64_t A[271828];

int64_t sum[271828];

void asumisu(int64_t res[4], int64_t hosei, const int64_t* data, int32_t size) {
	if (data[0] - hosei > data[size - 1] - data[0]) {
		res[0] = res[2] = data[0] - hosei;
		res[1] = res[3] = data[size - 1] - data[0];
	} else if (data[size - 2] - hosei <= data[size - 1] - data[size - 2]) {
		res[0] = res[2] = data[size - 2] - hosei;
		res[1] = res[3] = data[size - 1] - data[size - 2];
	} else {
		int32_t le = 0, greater = size - 2;
		while (le + 1 < greater) {
			int32_t mid = le + (greater - le) / 2;
			if (data[mid] - hosei <= data[size - 1] - data[mid]) le = mid; else greater = mid;
		}
		res[0] = data[le] - hosei;
		res[1] = data[size - 1] - data[le];
		res[2] = data[greater] - hosei;
		res[3] = data[size - 1] - data[greater];
	}
}

int main(void) {
	int32_t i;
	int64_t answer = -1;
	if (scanf("%" SCNd32, &N) != 1) return 1;
	for (i = 0; i < N; i++) {
		if (scanf("%" SCNd64, &A[i]) != 1) return 1;
	}
	sum[0] = A[0];
	for (i = 1; i < N; i++) {
		sum[i] = sum[i - 1] + A[i];
	}

	for (i = 2; i < N - 1; i++) {
		int64_t tomatu[4], sumipe[4];
		int j, k;
		asumisu(tomatu, 0, sum, i);
		asumisu(sumipe, sum[i - 1], sum + i, N - i);
		for (j = 0; j < 2; j++) {
			for (k = 0; k < 2; k++) {
				int64_t kitaeri[4];
				int64_t min, max, candidate;
				int l;
				kitaeri[0] = tomatu[j * 2 + 0];
				kitaeri[1] = tomatu[j * 2 + 1];
				kitaeri[2] = sumipe[k * 2 + 0];
				kitaeri[3] = sumipe[k * 2 + 1];

				min = max = kitaeri[0];
				for (l = 1; l < 4; l++) {
					if (kitaeri[l] < min) min = kitaeri[l];
					if (kitaeri[l] > max) max = kitaeri[l];
				}
				candidate = max - min;
				if (answer < 0 || candidate < answer) answer = candidate;
			}
		}
	}

	printf("%" PRId64 "\n", answer);
	return 0;
}

/*

#-----*------------#
------*-#--#--------

*----#-------------#
*-------#-------#---

*/
