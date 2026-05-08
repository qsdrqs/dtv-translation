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

int map[3000][3000];
int kyori[3000];
int douro[100000][3];

int main(void) {
	int smalls[3000];
	int visited[3000];
	int tyousataisyounum;
	int matinum;
	int douronum;
	int smallnum;
	int dourolen;
	int i;
	int from,to;
	int smallpos;
	int mincost,mincostto;
	int maxkyori;
	int nowkyori;
	int maekyori;
	scanf("%d %d %d",&matinum,&douronum,&smallnum);
	for(i=0;i<douronum;i++) {
		scanf("%d %d %d",&from,&to,&dourolen);
		douro[i][0]=from-1;
		douro[i][1]=to-1;
		douro[i][2]=dourolen;
		map[from-1][to-1]=dourolen;
		map[to-1][from-1]=dourolen;
	}
	for(i=0;i<smallnum;i++)scanf("%d",&smalls[i]);
	for(i=0;i<matinum;i++)kyori[i]=0x7fffffff;
	memset(visited,0,sizeof(visited));
	for(i=0;i<smallnum;i++) {
		smallpos=smalls[i]-1;
		kyori[smallpos]=0;
		//visited[smallpos]=1;
	}
	tyousataisyounum=smallnum;
	while(1) {
		mincost=0x7fffffff;
		mincostto=-1;
		for(i=0;i<matinum;i++) {
			if(!visited[i]) {
				if(kyori[i]<mincost) {
					mincost=kyori[i];
					mincostto=i;
				}
			}
		}
		if(mincostto>=0) {
			visited[mincostto]=1;
			for(i=0;i<matinum;i++) {
				if(map[i][mincostto]>0) {
					if(kyori[i]>kyori[mincostto]+map[i][mincostto]) {
						kyori[i]=kyori[mincostto]+map[i][mincostto];
					}
				}
			}
		} else break;
	}
	maxkyori=0;
	for(i=0;i<douronum;i++) {
		nowkyori=kyori[douro[i][0]];
		if(nowkyori<kyori[douro[i][1]]) {
			maekyori=nowkyori;
			nowkyori=kyori[douro[i][1]];
		} else maekyori=kyori[douro[i][1]];
		if(maekyori+douro[i][2]>nowkyori) {
			nowkyori=((douro[i][2]+nowkyori-maekyori)*5+5)/10;
			nowkyori+=maekyori;
		}
		if(maxkyori<nowkyori)maxkyori=nowkyori;
	}
	printf("%d\n",maxkyori);
	return 0;
}