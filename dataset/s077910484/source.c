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
int n,a,b,i;
scanf("%d",&n);
while(n-->0){
scanf("%d %d",&a,&b);
if(a>=0&&5>=a){
if(b>a){
for(i=a;i<b;i++)
printf("%d ",i);
printf("%d\n",b);
}
else {
for(i=a;i>b;i--)
printf("%d ",i);
printf("%d\n",b);
}
}
else {
if(b>5&&10>b&&b>a){
for(i=a;i<b;i++)
printf("%d ",i);
printf("%d\n",b);
}
else
if(b>=0&&5>=b){
for(i=a;i<10;i++)
printf("%d ",i);
for(i=5;i>b;i--)
printf("%d ",i);
printf("%d\n",b);
}
else
if(b>=6&&9>=b&&b<a){
for(i=a;i<10;i++)
printf("%d ",i);
for(i=5;i>0;i--)
printf("%d ",i);
for(i=0;i<b;i++)
printf("%d ",i);
printf("%d\n",b);
}
}
}
return 0;
}