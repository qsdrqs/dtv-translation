#include<stdio.h>
#define N 101

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
    int n, x;
    int l[N] = {0};
    int i;
    int d = 0;

    scanf("%d %d", &n, &x);
    for(i = 0; i < n; i++){
        scanf("%d", &l[i]);
    }

    for(i = 0; i < n + 1 && d <= x; i++){
        d += l[i];
    }

    printf("%d", i);

    return 0;
}