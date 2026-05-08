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

int MIN(int a,int b){return a<b?a:b;}
int b[10000010]={0};
int main(){
  int n,a,i;
  long long ans;
  scanf("%d",&n);
  for(i=0;i<n;i++){
    scanf("%d",&a);
    b[a]++;
  }
  for(i=ans=0;n;i++){
    ans+=MIN(n,i*4);
    n-=b[i];
  }
  printf("%lld\n",ans+1);
  return 0;
}