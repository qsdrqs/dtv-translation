#include <stdio.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

struct Team{
  int i,u,a,p;
}t[300],tmp;

int main(void){
  int i,j,n,total;
  int pass[1001];

  while(1){
    scanf("%d",&n);
    if(!n) break;

    memset(pass,0,sizeof(pass));
    for(i=0;i<n;i++){
      scanf("%d%d%d%d",&t[i].i,&t[i].u,&t[i].a,&t[i].p);
    }
    for(i=0;i<n-1;i++){
      for(j=i+1;j<n;j++){
	if(t[i].a < t[j].a || t[i].a==t[j].a && t[i].p > t[j].p || t[i].a==t[j].a && t[i].p==t[j].p && t[i].i > t[j].i){
	  tmp = t[i];
	  t[i] = t[j];
	  t[j] = tmp;
	}
      }
    }
    total = 0;
    for(i=0;i<n && total<26;i++){
      if(total < 10){
	if(pass[t[i].u] < 3){
	  printf("%d\n",t[i].i);
	  pass[t[i].u]++;
	  total++;
	}
      }
      else if(total < 20){
	if(pass[t[i].u] < 2){
	  printf("%d\n",t[i].i);
	  pass[t[i].u]++;
	  total++;
	}
      }
      else if(total < 26){
	if(pass[t[i].u] == 0){
	  printf("%d\n",t[i].i);
	  pass[t[i].u]++;
	  total++;
	}
      }
    }
  }

  return 0;
}