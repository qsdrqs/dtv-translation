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

int main(){
  int n,sum,i;
  sum = 0;

  while(1){
    scanf("%d",&n);
    if(n == 0) break;
    for(i=1;i*i <= n;i++){
      if(n % i == 0){
        if(i == 1) sum = 1;
        else if(n == i * i) sum += i;
        else sum += (i+(n / i));
      }
    }
    if(n == 1) sum = 0;
    if(n == sum) printf("perfect number\n");
    if(n > sum) printf("deficient number\n");
    if(n < sum) printf("abundant number\n");
  }

  return 0;
}