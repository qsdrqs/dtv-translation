#include<stdio.h>
#include<math.h>

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
  double x;
  int q;

  while(1){
    scanf("%d",&q);
    if(q<0)break;


    x = (double)q / 2.0;
    while(1){
      if(fabs(x*x*x-q) < 0.00001 * q)break;
      
      x = x - ((x*x*x)-q)/(3*x*x);
    }

    printf("%lf\n",x);
  }

  return 0;
}