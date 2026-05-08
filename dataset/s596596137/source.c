#include<stdio.h>
#include<stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct water{
  double t;
  int v;
} node;

int readInt(void){
  int c=getchar();
  while(!('0'<=c && c<='9')) c=getchar();
  int res=0;
  while('0'<=c && c<='9'){
    res=10*res+c-'0';
    c=getchar();
  }
  return res;
}

void run(void){
  int n,l;
  scanf("%d%d",&n,&l);
  node *q=(node *)calloc(n,sizeof(node));
  int front=0;
  int last=0;
  double t;
  int v;
  scanf("%lf%d",&t,&v);
  printf("%.7f\n",t);
  q[last++]=(node){t,v};
  double qtv=t*v;
  int i;
  for(i=1;i<n;i++){
    node in;
    in.t=readInt();
    in.v=readInt();
    int sum=0;
    node p=q[front];
    while(sum+p.v<=in.v){
      qtv-=p.v*p.t;
      sum+=p.v;
      front++;
      p=q[front];
    }
    if(sum<in.v){
      qtv-=q[front].t*(in.v-sum);
      q[front].v-=in.v-sum;
    }
    qtv+=in.t*in.v;
    while(front<last && q[last-1].t>in.t){
      last--;
      p=q[last];
      in=(node){(in.t*in.v+p.t*p.v)/(in.v+p.v),in.v+p.v};
    }
    q[last++]=in;
    printf("%.7f\n",qtv/l);
  }
}

int main(void){
  run();
  return 0;
}
