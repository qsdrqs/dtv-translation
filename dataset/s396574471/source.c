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

int width,height;
int result;
char map[102][103];
int map2[102][102];

int tansaku(int x,int y,int now_cost,int is_hori,int force_hori) {
	int here_is_hori;
	int tansaku_did=0;
	if(x<0 || x>width+1 || y<0 || y>height+1)return 0;
	if(force_hori && map[y][x]!='#')return 0;
	if(is_hori && map[y][x]!='#')now_cost++;
	if(map2[y][x]<=now_cost)return 0;
	map2[y][x]=now_cost;
	here_is_hori=(map[y][x]=='#');
	if(here_is_hori) {
		tansaku_did|=tansaku(x+1,y,now_cost,here_is_hori,1);
		tansaku_did|=tansaku(x,y+1,now_cost,here_is_hori,1)*2;
		tansaku_did|=tansaku(x-1,y,now_cost,here_is_hori,1)*4;
		tansaku_did|=tansaku(x,y-1,now_cost,here_is_hori,1)*8;
	}
	if(!(tansaku_did & 1))tansaku(x+1,y,now_cost,here_is_hori,0);
	if(!(tansaku_did & 2))tansaku(x,y+1,now_cost,here_is_hori,0);
	if(!(tansaku_did & 4))tansaku(x-1,y,now_cost,here_is_hori,0);
	if(!(tansaku_did & 8))tansaku(x,y-1,now_cost,here_is_hori,0);
	return 1;
}

int main(void) {
	int i,j;
	while(1) {
		scanf("%d%d",&width,&height);
		if(width==0 && height==0)break;
		memset(map,0,sizeof(map));
		for(i=1;i<=height;i++) {
			scanf("%s",&map[i][1]);
			map[i][0]='.';
			map[i][width+1]='.';
		}
		for(i=0;i<=width+1;i++) {
			map[0][i]='.';
			map[height+1][i]='.';
			for(j=0;j<=height+1;j++) {
				map2[j][i]=0x7fffffff;
			}
		}
		tansaku(0,0,0,0,0);
		for(i=1;i<=height;i++) {
			for(j=1;j<=width;j++) {
				if(map[i][j]=='&') {
					printf("%d\n",map2[i][j]);
					i=width+1;
					break;
				}
			}
		}
	}
	return 0;
}