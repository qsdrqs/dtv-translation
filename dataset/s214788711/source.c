#include<stdio.h>
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

int compare_int(const void *a, const void *b){
  return *(int*)a - *(int*)b;
}

int main(){ 
  int N, K, i;
  scanf("%d %d", &N, &K);
  
  int h[N];
  
  for(i = 0; i < N; i++){
    scanf("%d", &h[i]);
  }
  
  qsort(h, N, sizeof(int), compare_int);
  
  int min = 1000000000;
  
  for(i = 0; i < N-K+1; i++){
    if(h[i + K - 1] - h[i] < min){
      min = h[i + K - 1] - h[i];
    }
  }
                                                                                                  
  printf("%d\n", min);

  return 0;
}