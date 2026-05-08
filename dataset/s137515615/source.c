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

int main(){
    int i,j,k,n,m,l,a[100][100],b[100][100];
    long int c[100][100]={0};
    scanf("%d %d %d",&n,&m,&l);
    for(i=0;i<n;i++){
        for(j=0;j<m;j++){
            scanf("%d",&a[i][j]);
        }
    }
    for(i=0;i<m;i++){
        for(j=0;j<l;j++){
            scanf("%d",&b[i][j]);
        }
    }
    for(i=0;i<n;i++){
        for(j=0;j<l;j++){
            for(k=0;k<m;k++){
                c[i][j]+=a[i][k]*b[k][j];
            }
        }
    }
    for(i=0;i<n;i++){
        for(j=0;j<l;j++){
            if(j>0){
                printf(" ");
            }
            printf("%ld",c[i][j]);
        }
        printf("\n");
    }
    return 0;
}
