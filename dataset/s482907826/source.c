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

char ban[52][52];
int ans[52][52];
int main(void){
    int i,j,h,w,d,sum;
    int dx[8]={0,1,1,1,0,-1,-1,-1};
    int dy[8]={1,1,0,-1,-1,-1,0,1};
    for(i=0;i<52;i++){
        for(j=0;j<52;j++){
            ban[i][j]=0;
            ans[i][j]=0;
        }
    }
    scanf("%d %d",&h,&w);
    for(i=1;i<=h;i++){
        scanf("%s",&ban[i]);
        for(j=w;j!=0;j--){
            ban[i][j]=ban[i][j-1];
        }
        ban[i][0]=0;
    }
    for(i=1;i<=h;i++){
        for(j=1;j<=w;j++){
            sum=0;
            if(ban[i][j]=='#'){
                printf("#");
                continue;
            }
            for(d=0;d<8;d++){
                if(ban[i+dy[d]][j+dx[d]]=='#'){
                    sum++;
                }
            }
            printf("%d",sum);
        }
        printf("\n");
    }
    return 0;
}