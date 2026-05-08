//RUPC-C
#include<stdio.h>
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

char map[1005][1005];
int dx[]={1,0,-1,0};
int dy[]={0,1,0,-1};
typedef struct pair{
	int x,y;
}PAIR;
PAIR q[100005],sq[100005];
int bfs(int y,int x){
	int i,j,qn,sqn,nx,ny,f;
	q[0].y=y;q[0].x=x;
	qn=1;f=0;
	while(qn!=0){
		sqn=0;
		for(i=0;i<qn;i++){
			/*if(map[q[i].y][q[i].x]=='t'){
				f=1;
				goto nex;
			}*/
			map[q[i].y][q[i].x]='1';
			for(j=0;j<4;j++){
				nx=q[i].x+dx[j];
				ny=q[i].y+dy[j];
				if(map[ny][nx]=='t'){
					f=1;
					goto nex;
				}
				if(map[ny][nx]=='.' || map[ny][nx]=='t'){
					sq[sqn].x=nx;
					sq[sqn].y=ny;
					map[ny][nx]='1';
					sqn++;
				}
			}
		}
		//memcpy(q,sq,sizeof(PAIR)*sqn);
		for(i=0;i<sqn;i++){
			q[i].x=sq[i].x;
			q[i].y=sq[i].y;
		}
		qn=sqn;
	}
	nex:
	if(f==1)return 1;
	else return 0;
}
int main(){
	int i,j,w,h,n,ans=0,f=0;
	int x,y,sx,sy;
	char ss[1005];
	scanf("%d%d",&w,&h);
	for(i=0;i<=w+1;i++)map[0][i]=map[h+1][i]='#';
	for(i=1;i<=h;i++){
		scanf("%s",ss);
		strcpy(map[i]+1,ss);
		map[i][0]=map[i][w+1]='#';
	}
	//for(i=0;i<=h+1;i++)printf("%s\n",map[i]);
	map[1][1]='1';
	if(bfs(1,1)==1)f=1;
	scanf("%d",&n);
	for(i=0;i<n;i++){
	//while(scanf("%d%d",&x,&y)!=EOF){
		if(f==0)ans++;
		scanf("%d%d",&x,&y);
		x++;y++;
		map[y][x]='.';
		sx=sy=1;
		for(j=0;j<4;j++)
			if(map[y+dy[j]][x+dx[j]]=='1')break;
		if(j<4)sx=x,sy=y;
		map[sy][sx]='1';
		if(f==0 && j<4 && bfs(sy,sx)==1)f=1;
		
		//printf("%d:%d %d\n",i+1,sx,sy);
		//for(j=0;j<=h+1;j++)printf("%s\n",map[j]);
		//printf("\n");
	}
	if(f==0)printf("-1\n");
	else printf("%d\n",ans);
	return 0;
}