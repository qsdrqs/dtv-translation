#include <stdio.h>
#include <math.h>
#include <ctype.h>
#define square(x) ((x) * (x))

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int hexa(char s);

int main(void) {
    int red,green,blue,num,i,color[8][3]={{0,0,0},{0,0,255},{0,255,0},{0,255,255},{255,0,0},{255,0,255},{255,255,0},{255,255,255}};
    char temp[8],colorname[9][8]={"black","blue","lime","aqua","red","fuchsia","yellow","white"};
    double min,dis;
    while (scanf(" %s",temp)!=EOF&&temp[0]!='0') {
        min=221952.0;
        red=hexa(temp[1])*16+hexa(temp[2]);
        green=hexa(temp[3])*16+hexa(temp[4]);
        blue=hexa(temp[5])*16+hexa(temp[6]);
        for (i=0; i<8; i++) {
            dis = square(color[i][0]-red)+square(color[i][1]-green)+square(color[i][2]-blue);
            if (dis<min) {
                min=dis;
                num=i;
            }
        }
        printf("%s\n",colorname[num]);
    }
    return 0;
}

int hexa(char s) {
    if (isalpha(s)) {
        return s-'a'+10;
    } else {
        return s-'0';
    }
}