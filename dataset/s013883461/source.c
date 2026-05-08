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

int main(){
  int unused __attribute__((unused));
  int X, A, B;
  unused = scanf("%d %d %d", &X, &A, &B);

  if(B-A <= 0) printf("delicious");
  else if(B-A <= X) printf("safe");
  else printf("dangerous");

  return 0;
}