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

int main(void)
{
    long long n,nc;
    long long sum=0;
    scanf("%lld",&n);
    nc=n;

    while(n>0){
        sum+=n%10;
        n/=10;
    }

    if(nc%sum==0){
        puts("Yes");
    }else{
        puts("No");
    }

    return 0;
}