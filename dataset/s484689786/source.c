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

  long n;
  scanf("%ld", &n);
  long a[n];
  for (long i = 0; i < n; i++) {
    scanf("%ld", &a[i]);
  }
  long sum = 0;
  for (long i = 0; i < n; i++) {
    sum += a[i];
  }
  if (sum%2 == 0) {
    printf("YES\n");
  } else {
    printf("NO\n");
  }

  return 0;
}