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

int main(void){
    int N, i, sum=0, x;
    scanf("%d", &N);
    for(i=0; i<N; i++){
        scanf("%d", &x);
        if(x % 2 == 0){
            sum++;
        }
    }
    printf("%d\n", sum);
    return 0;
}

 
