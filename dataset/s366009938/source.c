#include <stdio.h>
#include <stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int compare_int(const void *a, const void *b)
{
    return *(int*)a - *(int*)b;
}

int main(void)
{
    int N, i, f=0;
    long long int A[200002];

    scanf("%d",&N);
    for(i=0; i<N; i++){
        scanf("%lld",&A[i]);
    }

    qsort(A,N,sizeof(long long int),compare_int);

    for(i=0; i<N-1; i++){
        if(A[i] == A[i+1]){
            f=1;
        }
        //printf("%lld ",A[i]);
    }

    if(f==1){
        printf("NO\n");
    } else {
        printf("YES\n");
    }

    return 0;
}