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

  int n;
  double x[2], y[2], r[2];
  double d;


  scanf("%d", &n);
  while(n>0){
   
    scanf("%lf %lf %lf %lf %lf %lf", &x[0], &y[0], &r[0], &x[1], &y[1], &r[1]);

    d=pow(pow(x[1]-x[0], 2)+pow(y[1]-y[0], 2), 0.5);
    
    if(r[0]+r[1]<d){
      printf("0\n");
    }
    else if(d<r[0]-r[1]){
      printf("2\n");
    }
    else if(d<r[1]-r[0]){
      printf("-2\n");
    }
    else{
      printf("1\n");
    }

    n--;
  }

  return(0);
}

