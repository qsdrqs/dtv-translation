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

int main()
{
  int i,a[100],ans = 0;

  for(i = 0;i < 5;i++){
    scanf("%d",&a[i]);
  }

  for(i = 0;i < 5;i++){
    if(a[i] < 40){
      a[i] = 40;
    }
    ans += a[i];
  }

  printf("%d\n",ans/5);

  return 0;
}