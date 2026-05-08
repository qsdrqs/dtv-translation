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

int main(void){
  long long int x,y;

  scanf("%lld", &x); scanf("%lld", &y);

  if(x-y==1||x-y==-1||x-y==0)
    puts("Brown");
    else
    puts("Alice");
    
  return 0;
}