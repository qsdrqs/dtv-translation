#include <stdio.h>

#define N_MAX   100000
#define W_MAX   100000
#define H_MAX   100000

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int MIN(int a,int b){return a<b?a:b;}
int MAX(int a,int b){return a<b?b:a;}

int width[W_MAX+1]    = {};
int height[H_MAX+1]   = {};

int main(void){
    int N,W,H,x,y,w;
    int i,j;
    int M;
    
    scanf("%d %d %d",&N,&W,&H);
    for( i=0; i<N; i++){
        scanf("%d %d %d",&x,&y,&w);
        width[MAX(0,   x-w)]++;
        width[MIN(H+1, x+w)]--;
        height[MAX(0,  y-w)]++;
        height[MIN(W+1,y+w)]--;
    }
    
    M=N;
    for( i=0; i<W; i++){
        if( M > width[i] ){
            M = width[i];
        }
        width[i+1] += width[i];
    }
    
    if( M <= 0 ){
        M = N;
        for( i=0; i<H; i++){
            if( M > height[i] ){
                M = height[i];
            }
            height[i+1] += height[i];
        }
    }
    
    if( M <= 0 ){
        printf("No\n");
    }else{
        printf("Yes\n");
    }
}


