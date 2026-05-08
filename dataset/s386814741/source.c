#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main() {
    int i,red,green,blue,k;
    scanf("%d%d%d",&red,&green,&blue);
    scanf("%d",&k);

    for(i=0;i<k;i++){
        if(blue<=green){
            blue*=2;
        }else if(green<=red){
            green*=2;
        }else{
            blue*=2;
        }
    }
    if(green>red && blue>green){
        printf("Yes");
    }else{
        printf("No");
    }
    return 0;
}