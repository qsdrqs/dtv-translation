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

int cmpnum(const void * n1, const void * n2)
{
	if (*(long *)n1 > *(long *)n2)
	{
		return 1;
	}
	else if (*(long *)n1 < *(long *)n2)
	{
		return -1;
	}
	else
	{
		return 0;
	}
}

int main(void){

  long n;
  scanf("%ld", &n);
  long a[n], b[n], c[n];
  for (long i = 0; i < n; i++) {
    scanf("%ld", &a[i]);
  }
  for (long i = 0; i < n; i++) {
    scanf("%ld", &b[i]);
  }
  for (long i = 0; i < n; i++) {
    scanf("%ld", &c[i]);
  }
  qsort(a, n, sizeof(long), cmpnum);
  qsort(b, n, sizeof(long), cmpnum);
  qsort(c, n, sizeof(long), cmpnum);

  long a_b[n];
  long mark_a = 0;
  for (long i = 0; i < n; i++) {
    while (mark_a < n) {
      if (a[mark_a] >= b[i]) {
        a_b[i] = mark_a;
        break;
      } else {
        mark_a++;
      }
    }
    if (mark_a == n) {
      a_b[i] = n;
    }
  }

  long a_b_c[n];
  long mark_b = 0;
  long sum = 0;
  for (long i = 0; i < n; i++) {
    a_b_c[i] = sum;
    while (mark_b < n) {
      if (b[mark_b] >= c[i]) {
        break;
      } else {
        a_b_c[i] += a_b[mark_b];
        sum = a_b_c[i];
        mark_b++;
      }
    }
    if (mark_b == n) {
      a_b_c[i] = sum;
    }
  }
  sum = 0;
  for (long i = 0; i < n; i++) {
    sum += a_b_c[i];
  }
  printf("%ld\n", sum);

  return 0;
}