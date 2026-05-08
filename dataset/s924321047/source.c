#include<stdio.h>
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
    char a[1000];
    int i,sum;
    while(1)
    {
        scanf("%s",&a);
        if(a[0]=='0')
        {
            return 0;
        }
        sum = 0;
        for(i=0;a[i]!='\0';i++)
        {
            sum+=a[i]-'0';
        }
        printf("%d\n",sum);
}
return 0;
    }

