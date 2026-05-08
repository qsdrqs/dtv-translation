#include <stdio.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main(void) {
  int A, B, K;
  scanf("%d %d %d", &A, &B, &K);

  for(int i = 0; i < K; i++) {
    // takahashi
    if((i % 2) == 0) {
      if(A % 2) {
	A--;
      }
      B += A / 2;
      A /= 2;
    } else {
      // aoki
      if(B % 2) {
	B--;
      }
      A += B / 2;
      B /= 2;
    }
  }

  printf("%d %d\n", A, B);

  return 0;
}
