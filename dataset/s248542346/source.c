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

int main(){
  int m,n,s,t,a,b,i,j;
  double d,min=1.0*1e9;//printf("%f\n",min);
  scanf("%d %d %d %d %d %d",&m,&n,&s,&t,&a,&b);
  for(i=0;i<=n;i+=a){
    for(j=0;i+j<=n;j+=b){
      if(i+j==0)continue;
      d=1.0*(s*i+t*j)/(i+j);//printf("%f\n",m-d);
      if(min>fabs(m-d))min=fabs(m-d);//printf("%f %f %f\n",d,min,fabs(m-d));
    }
  }
  printf("%f\n",min);
  return 0;
}