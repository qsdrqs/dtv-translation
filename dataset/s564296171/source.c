#include<stdio.h>
#include<stdlib.h>
#include<stdbool.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

long long llmax(long long a,long long b){if(a>b){return a;}return b;}
long long llmin(long long a,long long b){if(a<b){return a;}return b;}
long long llzt(long long a,long long b){return llmax(a,b)-llmin(a,b);}
long long llgcd(long long a,long long b){long long c;while(b!=0){c=a%b;a=b;b=c;}return a;}
int llsortfncsj(const void *a,const void *b){if(*(long long *)a>*(long long *)b){return 1;}if(*(long long *)a==*(long long *)b){return 0;}return -1;}

bool isprime(long long x){
  long long i;
  if(x==1){return false;}
  if(x==2){return true;}
  if(x%2==0){return false;}
  for(i=3;i*i<=x;i+=2){
    if(x%i==0){return false;}
  }
  return true;
}

long long calcmod(long long x,long long m){
  if(x>=0){return x%m;}
  return (m-((-x)%m))%m;
}

long long n,a[16384];

bool judge(long long p){
  if(p==1 || p==0){return false;}
  //printf("try:%lld\n",p);
  if(calcmod(a[0],p)!=0){return false;}
  if(!isprime(p)){return false;}
  long long i,b[16384],t=-1;
  for(i=0;i<=n;i++){
    b[i]=calcmod(a[i],p);
    if(b[i]!=0){t=i;}
  }
  if(t==-1){return true;}
  if(p>t){return false;}
  for(i=n;i>=p;i--){
    b[i-(p-1)]+=b[i];
    b[i-(p-1)]%=p;
  }
  for(i=p-1;i>=0;i--){
    if((b[i]%p)!=0){return false;}
  }
  return true;
}

int main(){
  long long i,g;
  long long res[16384],rp=0,t;
  scanf("%lld",&n);
  for(i=n;i>=0;i--){scanf("%lld",&a[i]);}
  g=llzt(0,a[n]);
  for(i=n-1;i>=0;i--){
    g=llgcd(g,llzt(0,a[i]));
  }
  for(i=2;i*i<=g;i++){
    if((g%i)!=0){continue;}
    if(judge(i)){res[rp]=i;rp++;}
    while((g%i)==0){g/=i;}
  }
  if(judge(g)){res[rp]=g;rp++;}
  for(i=2;i<=n;i++){
    if(judge(i)){res[rp]=i;rp++;}
  }
  qsort(res,rp,sizeof(long long),llsortfncsj);
  res[rp]=-1;
  for(i=0;i<rp;i++){
    if(res[i]==res[i+1]){continue;}
    printf("%lld\n",res[i]);
  }
  return 0;
}
