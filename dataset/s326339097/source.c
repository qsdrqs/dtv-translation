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

int main () {
  int n, a[100], i, v, j, k;

  scanf("%d", &n);
  for(i = 0 ; i < n ; i++) {
    scanf("%d", &a[i]);
  }
  for(i = 0 ; i < n ; i++) {
    printf("%d", a[i]);
    if(i != n-1) printf(" ");
  }
  printf("\n");

  for(i = 1 ; i <= n-1 ; i++) {
    v = a[i];
    j = i - 1;
    while(j >= 0 && a[j] > v){
      a[j+1] = a[j];
      j--;  
    }
    a[j+1] = v;
    for(k = 0 ; k < n ; k++) {
      printf("%d", a[k]);
      if(k != n-1) printf(" ");
    }
    printf("\n");
  }
  return 0;
}