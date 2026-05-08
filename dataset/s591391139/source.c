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
    int i,j,k,count=0;
    long int x;

    scanf("%ld",&x);

    for(i=x;i<100004;i++){
        for(j=2;j<x/2;j++){
            if(x%j==0){
                count++;
            }
        }
        if(count>0){
            x++;
            count=0;
        }
        else{
            break;
        }
    }

    printf("%ld",x);

    return 0;
}
