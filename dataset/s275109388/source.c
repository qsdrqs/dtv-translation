#include<stdio.h>
#include<stdlib.h>
#include<math.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef long long int int64;

#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define ABS(a) ((a)>(0)?(a):-(a))

typedef struct point2d{
  int64 x,y;
} point;

typedef struct line2d{
  point s,t;
} line;

void swap(int64 *a,int64 *b){
  int64 tmp=*a;
  *a=*b;
  *b=tmp;
}

int func(const line *a,const point *b){
  int64 p=a->s.x;
  int64 q=a->s.y;
  int64 r=a->t.x;
  int64 s=a->t.y;
  int64 t=(s-q)*(b->x-p)-(r-p)*(b->y-q);
  return t==0?0:(t>0?1:-1);
}

void calcCrossPoint(const line *a,const line *b,double *x,double *y){
  if(0==func(a,&(b->s))){
    *x=b->s.x;
    *y=b->s.y;
    return;
  }
  if(0==func(a,&(b->t))){
    *x=b->t.x;
    *y=b->t.y;
    return;
  }
  if(0==func(b,&(a->s))){
    *x=a->s.x;
    *y=a->s.y;
    return;
  }
  if(0==func(b,&(a->t))){
    *x=a->t.x;
    *y=a->t.y;
    return;
  }
  double p=a->t.y-a->s.y;
  double q=-(a->t.x-a->s.x);
  double r=b->t.y-b->s.y;
  double s=-(b->t.x-b->s.x);
  double z=a->s.x*a->t.y-a->s.y*a->t.x;
  double w=b->s.x*b->t.y-b->s.y*b->t.x;
  double det=p*s-q*r;
  *x=(s*z-q*w)/det;
  *y=(-r*z+p*w)/det;
  return;
}

void scanfLine(line *a){
  scanf("%lld%lld%lld%lld",&(a->s.x),&(a->s.y),&(a->t.x),&(a->t.y));
  return;
}

void run(void){
  int q;
  scanf("%d",&q);
  while(q--){
    line a,b;
    scanfLine(&a);
    scanfLine(&b);
    double x,y;
    calcCrossPoint(&a,&b,&x,&y);
    printf("%.9lf %.9lf\n",x,y);    
  }
}

int main(void){
  run();
  return 0;
}

