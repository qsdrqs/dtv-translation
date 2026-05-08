#include <stdio.h>
#include <string.h>
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
    int N, M, b_fase=0;
    char A[50][50], B[50][50];
    scanf("%d%d", &N, &M);
    for (int i=0; i<N; i++) scanf("%s", A[i]);
    for (int i=0; i<M; i++) scanf("%s", B[i]);

    for(int i=0; i<N; i++){
        for(int j=0; j<=N-M; j++){
            if(strncmp(A[i]+j, B[0], M)==0){
                for(int k=0; k<M; k++){
                    if(strncmp(A[i+k]+j, B[k], M)!=0) break;
                    if(k==M-1){
                        printf("Yes");
                        return 0;
                    }
                }
            }
        }
    }
    printf("No");
    return 0;
}