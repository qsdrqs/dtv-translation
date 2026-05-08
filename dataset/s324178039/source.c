#include<stdio.h>
#include<stdlib.h>
#include<string.h>
#define df 0


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
  int n;
  scanf("%d",&n);

  long int a,b,c=0;
  if(n%2==0){
    a=n;b=n;c=n/2;
  }else if(n%3==0){
    a=n/3;b=n*2;c=n*2;
  }
   else {
    for(a=3*n/4;a>0;a--){
      for(b=2*a*n/(4*a-n);b>0 && 4*a*b>n*(a+b) ;b--){
	if(n*a*b%(4*a*b-n*a-n*b)==0){
	  c=n*a*b/(4*a*b-n*a-n*b);
	  break;
	}
      }
      if(c)break;
    }
  }

  printf("%ld %ld %ld",a,b,c);
  return 0;
}


/// confirm df==0 ///
