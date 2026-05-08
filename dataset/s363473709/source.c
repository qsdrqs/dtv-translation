#include<stdio.h>
#include<stdlib.h>
#include<string.h>
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
	int n;
	int i,j=0,k=30;
	char az[26];
	char str[1025];
	char queue[60];
	scanf("%d",&n);
	for(i=0;i<n;i++){
		k=30;
		memset(az,0,26);
		memset(str,0,1025);
		memset(queue,0,60);
		scanf("%s",str);
		for(j=0;j<1025;j+=3){
			if(az[str[j]-'a']==0&&str[j]!=0){
				az[str[j]-'a']=1;
				queue[k]=str[j];			
			}
			else if(str[j]=='\0'){break;}
			switch(str[j+2]){
				case '>':
					k++;
					break;
				case '-':
					k--;
					break;
				default:
					break;
			}
		}
		for(j=0;j<60;j++){
			if(queue[j]){
				printf("%c",queue[j]);
			}
		}
		puts("");
	}
	
	return 0;
}