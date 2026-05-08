#include <stdio.h>
#include <ctype.h>
 
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int from_mcxi(const char* mcxi) {
    const char* nowp=mcxi;
    int num=1;
    int result=0;
    for(;*nowp;nowp++) {
        switch(*nowp) {
            case 'm':
                result+=1000*num;
                num=1;
                break;
            case 'c':
                result+=100*num;
                num=1;
                break;
            case 'x':
                result+=10*num;
                num=1;
                break;
            case 'i':
                result+=1*num;
                num=1;
                break;
            default:
                if(isdigit(*nowp))num=*nowp-'0';
        }
    }
    return result;
}
 
void to_mcxi(char* mcxi,int num) {
    if(num>=1000) {
        if(num>=2000)*(mcxi++)=(num/1000)+'0';
        *(mcxi++)='m';
        num%=1000;
    }
    if(num>=100) {
        if(num>=200)*(mcxi++)=(num/100)+'0';
        *(mcxi++)='c';
        num%=100;
    }
    if(num>=10) {
        if(num>=20)*(mcxi++)=(num/10)+'0';
        *(mcxi++)='x';
        num%=10;
    }
    if(num>=1) {
        if(num>=2)*(mcxi++)=(num/1)+'0';
        *(mcxi++)='i';
        num%=1;
    }
    *mcxi=0;
}
 
int main(void) {
    int data_num,now_data;
    char q1[100],q2[100],ans[100];
    scanf("%d",&data_num);
    for(now_data=0;now_data<data_num;now_data++) {
        scanf("%s%s",q1,q2);
        to_mcxi(ans,from_mcxi(q1)+from_mcxi(q2));
        puts(ans);
    }
    return 0;
}