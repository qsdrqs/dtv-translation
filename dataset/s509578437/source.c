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
    int n;
    scanf("%d", &n);
    int a[n+1];
    for ( int i = 1; i <= n; i++ ) {
        scanf("%d", &a[i]);
    }
    int cnt=0;
    for ( int i = 1; i <= n; i++ ) {
        if ( a[i] == i ) {
            int tmp = a[i];
            a[i] = a[i+1];
            a[i+1] = tmp;
            cnt += 1;
        }
    }
    printf("%d\n", cnt);
    return 0;
}