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
    int x,y,x1,y1,a,b,i;
    scanf("%d %d %d %d",&x,&y,&x1,&y1);
    a=y1-y;
    b=x1-x;
    for(i=0;i<a;i++)
    {
        printf("U");
    }
    for(i=0;i<b;i++)
    {
        printf("R");
    }
    for(i=0;i<a;i++)
    {
        printf("D");
    }
    for(i=0;i<=b;i++)
    {
        printf("L");
    }
    for(i=0;i<=a;i++)
    {
        printf("U");
    }
    for(i=0;i<=b;i++)
    {
        printf("R");
    }
    printf("DR");
    for(i=0;i<=a;i++)
    {
        printf("D");
    }
    for(i=0;i<=b;i++)
    {
        printf("L");
    }
    printf("U");
    return 0;
}
