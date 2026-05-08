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

void intstr(int n,char* s){
  int i,j=0;
  for(i=n;i  ;i/=10)s[++j]=0;
  for(i=n;j--;i/=10)s[j]=i%10+'0';
}
int f(int a){
  char s[10];
  int l=0,i;
  intstr(a,s);//printf("%s ",s);
  while(s[l++]);//printf("%d\n",l);
  for(i=0;2*i<l;i++){
    if(s[i]-s[l-i-2])return 1;
  }
  printf("%d\n",a);
  return 0;
}  
int main(){
  int i,n;
  scanf("%d",&n);
  for(i=0;f(n-i)&&f(n+i);i++);
  return 0;
}