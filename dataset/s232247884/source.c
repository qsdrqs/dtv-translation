#include <stdio.h>
#define MAX 7368792

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int isPrime[MAX];

int main(void) {
  int m, n, i, j, count;
  while (1) {
    scanf("%d %d", &m, &n);
    if (m == 0 && n == 0) return 0;
    for (i = 0; i < MAX; i++)
      isPrime[i] = 1;

    count = 0;
    for (i = m; ; i++) {
      if (isPrime[i]) {
	if (count == n) break;
	count++;
	for (j = 1; i * j < MAX; j++) {
	  isPrime[i * j] = 0;
	}
      }
    }
    printf("%d\n", i);
  }
}