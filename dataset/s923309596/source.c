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

int main(void) {
  long long int k, i, j, min = 2, max = 3;
  scanf("%lld", &k);
  int a[k];
  for(i = 0; i < k; ++i) scanf("%d", &a[i]);
  if(a[k - 1] != 2) {
    printf("-1");
    return 0;
  }
  for(i = k - 2; i >= 0; --i) {
    long long int d1, d2;
    d1 = min / a[i];
    d2 = max / a[i];
    if(d1 == d2 && min % a[i]) {
      printf("-1");
      return 0;
    }
    d1 = (min + a[i] - 1) / a[i];
    min = d1 * a[i];
    max = d2 * a[i] + a[i] - 1;
    //printf("%d %d\n", min, max);
  }
  printf("%lld %lld", min, max);
  return 0;
}