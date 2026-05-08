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

int main(void){
	int n,l,tun[102],pos[21],dir[21],sec,i,j,last,exit;
	char x[9];
	while(1){
		for(i=0;i<102;i++){
			tun[i]=0;
		}
		for(i=0;i<21;i++){
			pos[i]=dir[i]=0;
		}
		sec=0;
		exit=0;
		scanf("%d %d",&n,&l);
		if(n==0&&l==0){
			break;
		}
		for(i=1;i<=n;i++){
			scanf("%s %d",&x,&pos[i]);
			if(x[0]=='R'){
				dir[i]=1;
			}
			else{
				dir[i]=-1;
			}
		}
		while(1){
			sec++;
			for(i=1;i<=n;i++){
				if(pos[i]==1000){
					continue;
				}
				pos[i]+=dir[i];
				tun[pos[i]]++;
			}
			for(i=1;i<l;i++){
				if(tun[i]>1){
					for(j=1;j<=n;j++){
						if(pos[j]==i){
							dir[j]=dir[j]*(-1);
						}
					}
				}
			}
			if(tun[l]!=0||tun[0]!=0){
				for(i=1;i<=n;i++){
					if(pos[i]==l){
						pos[i]=1000;
						dir[i]=0;
						last=i;
						exit++;
						break;
					}
				}
				if(exit==n){
					break;
				}
				for(i=1;i<=n;i++){
					if(pos[i]==0){
						pos[i]=1000;
						dir[i]=0;
						last=i;
						exit++;
						break;
					}
				}
				if(exit==n){
					break;
				}
			}
			for(i=0;i<102;i++){
				tun[i]=0;
			}
		}
		printf("%d %d\n",sec,last);
	}
	return 0;
}