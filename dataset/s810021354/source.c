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

int main(void){
    int a, b, c;
    scanf("%d %d %d",&a,&b,&c);
    int count=0;
    for(int i=a;i<=b;i++){
        if(c%i==0)count++;
    }
    
printf("%d\n", count);
return 0;
}
