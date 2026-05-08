#include <stdio.h>
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
  int wall[100],wide,q,i,j,k,needwide,id,c,flag,m;
  char sorw[2];
  while(1){
    scanf("%d%d",&wide,&q);
    if(wide==0&&q==0) break;
    for(i=0;i<wide;i++){
      wall[i]=-1;
    }
    for(i=0;i<q;i++){
      scanf("%s",sorw);
      if(sorw[0]=='s'){
	scanf("%d%d",&id,&needwide);
	c=0;
	flag=0;
        for(j=0,m=0;j<wide;j++){
          if(wall[j]==-1){
	    c++;
            if(c==needwide){
              flag=1;
	      break;
	    }
	  }
          else if(wall[j]!=-1){
	    c=0;
            m=j+1;
	  }
	}
	if(flag==1){
	  for(k=m;k<m+needwide;k++){
            wall[k]=id;
	  }
	  printf("%d\n",m);
	}
        else if(flag==0){
          printf("impossible\n");
	}
      }
      else if(sorw[0]=='w'){
        scanf("%d",&id);
        for(j=0;j<wide;j++){
          if(wall[j]==id) wall[j]=-1;
	}
      }

    }
    printf("END\n");
  } 
  return 0;
}