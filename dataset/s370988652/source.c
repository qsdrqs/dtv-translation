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
    int i;
    
    int n;
    scanf("%d\n",&n);
    int a[n];
    for(i=0;i<n;i++)scanf("%d ",&a[i]);
    
    int m;
    scanf("%d\n",&m);
    if(m>n){
        printf("0\n");
        return 0;
    }
    int b[m];
    for(i=0;i<m;i++)scanf("%d ",&b[i]);
    
    int j;
    for(i=0,j=0;i<m;i++){
        for(;j<n;j++){
            if(a[j]==b[i])break;
            else if(a[j]>b[i]){
                printf("0\n");
                return 0;
            }
        }
        if(m-i>n-j){
            printf("0\n");
            return 0;
        }
    }
    
    printf("1\n");
    
    return 0;
}

