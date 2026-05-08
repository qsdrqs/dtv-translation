#include <stdio.h>
#include <math.h>

#define M_PI 3.14159265358979323846
 
 
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
    double PI=M_PI;
    double p=PI*2/1000000;

    int N;
    double x[100],y[100];
    int kakuritu[100] ={};

    scanf("%d",&N);
    for(int i=0; i<N; i++)
        scanf("%lf %lf",&x[i],&y[i]);

    for(int i=0; i<1000000; i++) {
        double max = cos(i*p)*x[0]+sin(i*p)*y[0];
        int maxj=0;
        for(int j=0; j<N; j++) {
            if(max < cos(i*p)*x[j]+sin(i*p)*y[j]) {
                max = cos(i*p)*x[j] + sin(i*p)*y[j];
                maxj=j;
            }
        }
        kakuritu[maxj]++;
    }

    for(int i=0;i<N;i++) {
        printf("%.10f\n",(double)kakuritu[i]/1000000.0);
    }
    return 0;
}