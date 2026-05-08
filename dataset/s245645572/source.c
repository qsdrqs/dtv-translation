#include "stdio.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main(int argc, char const *argv[]) {
  int N,K;
  scanf("%d%d",&N,&K );
  if (K<=(int)((N+1)/2)) {
    printf("YES");
  }else{
    printf("NO");
  }
  return 0;
}
