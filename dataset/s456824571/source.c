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
  double a, s, t;
  int i;
  
  while(scanf("%lf", &a) != EOF) {
    s = a;
    t = a;
    for (i = 2; i <= 10; i++) {
      if (i % 2)
	t /= 3.0;
      else
	t *= 2.0;
      s += t;
    }
    printf("%.7lf\n", s);
  }
  return 0;
}