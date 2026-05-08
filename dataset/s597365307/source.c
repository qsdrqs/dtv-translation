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

int main(void){

  long n,a,b;
  scanf("%ld %ld %ld", &n, &a, &b);

  long dif = b-a;
  long tohead,totail;
  long round;
  if (dif%2 == 0) {
    round = dif/2;
  } else {
    tohead = a-1;
    totail = n-b;
    round = tohead;
    if (totail < tohead) {
      round = totail;
    }
    round++;
    dif--;
    round += dif/2;
  }

  printf("%ld\n", round);

  return 0;
}