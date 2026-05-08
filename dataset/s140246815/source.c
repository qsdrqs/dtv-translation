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

int main(void){
	int N;
	char S[101];
	scanf("%d",&N);
	int i,ans=0;
	scanf("%s",S);				//ここ！文字列読み取りだけならこれでよい
	
	int cut = 1;
	int memo=0;
	int lFlag=0,rFlag=0;
	
	while(cut <= N){
		memo = 0;
		char target; // 'a' = 97
		for(target='a';target<='z';target++){
			for(i=0;i<cut;i++){
				if(S[i] == target){
					lFlag = 1;
				}
			}
			for(i=cut;i<N;i++){
				if(S[i] == target){
					rFlag = 1;
				}
			}
			if(lFlag==1 && rFlag == 1){
				memo++;
			}
			lFlag=0;rFlag=0;
		}
		if(memo >= ans){
			ans = memo;
		}
		cut++;
	}
	
	printf("%d",ans);
	return 0;}