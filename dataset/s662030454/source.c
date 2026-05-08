#include <stdio.h>
#include <math.h>
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
  int x,h;
  double s,r;
  for(;;){
    scanf("%d\n%d",&x,&h);
    if(x==0 && h==0) break;
    r = (double)x / 2;
    r = sqrt(r*r + h*h);
    s = x*x + 2*x*r;
    printf("%.6lf\n",s);
  }
  return 0;
}