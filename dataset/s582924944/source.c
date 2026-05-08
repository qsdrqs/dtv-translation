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

int main() {
    int a, b;
    scanf("%d %d", &a, &b);
    if(a < b){
        for(int i=0;i<b;++i){
            printf("%d", a);
        }
    }
    else{
        for(int i=0;i<a;++i){
            printf("%d", b);
        }
    }
    printf("\n");
}
