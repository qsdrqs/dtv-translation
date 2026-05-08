#include <stdio.h>
#include <math.h>
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
    // Your code here!
    int x[10][10];
    int n,d;
    int count=0;
    scanf("%d %d",&n,&d);
    for(int i=0;i<n;i++){
        for(int j=0;j<d;j++){
            scanf("%d",&x[i][j]);//printf("%d\n",x[i][j]);
        }
        
        for(int k=i-1;k>=0;k--){
            double p=0;
            for(int j=0;j<d;j++){
                p+=powf((x[k][j]-x[i][j]),2);
                //printf("%f\n",powf((x[k][j]-x[i][j]),2));
            }
            p=sqrt(p);
            if(floor(p)==p)count++;
        }
    }
    printf("%d\n",count);
    return 0;
}
