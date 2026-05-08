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

int map[10][10];
int m,n;

int chousa(int kx,int ky,int nokori) {
	int x,y;
	int result=0;
	int house=0;
	if(nokori<0)return 0;
	if(map[kx][ky]==1) {/*今いる家を通ったことにする*/
		map[kx][ky]=0;
		house=1;
	}
	/*左に道順を調査*/
	for(x=kx-1;x>=0;x--) {
		/*家に降りる*/
		if(map[x][ky]==1) {
			result+=chousa(x,ky,nokori-1);
			break;/*家の上を通る場合には必ずプレゼントを拾う*/
		}
		/*教会に戻る*/
		else if(map[x][ky]==2 && nokori==0) {
			result++;
			if(house)map[kx][ky]=1;/*通った家を元に戻す*/
			return result;
		}
		/*通れない*/
		else if(map[x][ky]==3)break;
	}
	/*右に道順を調査*/
	for(x=kx+1;x<m;x++) {
		/*家に降りる*/
		if(map[x][ky]==1) {
			result+=chousa(x,ky,nokori-1);
			break;/*家の上を通る場合には必ずプレゼントを拾う*/
		}
		/*教会に戻る*/
		else if(map[x][ky]==2 && nokori==0) {
			result++;
			if(house)map[kx][ky]=1;/*通った家を元に戻す*/
			return result;
		}
		/*通れない*/
		else if(map[x][ky]==3)break;
	}
	/*上に道順を調査*/
	for(y=ky-1;y>=0;y--) {
		/*家に降りる*/
		if(map[kx][y]==1) {
			result+=chousa(kx,y,nokori-1);
			break;/*家の上を通る場合には必ずプレゼントを拾う*/
		}
		/*教会に戻る*/
		else if(map[kx][y]==2 && nokori==0) {
			result++;
			if(house)map[kx][ky]=1;/*通った家を元に戻す*/
			return result;
		}
		/*通れない*/
		else if(map[kx][y]==3)break;
	}
	/*下に道順を調査*/
	for(y=ky+1;y<n;y++) {
		/*家に降りる*/
		if(map[kx][y]==1) {
			result+=chousa(kx,y,nokori-1);
			break;/*家の上を通る場合には必ずプレゼントを拾う*/
		}
		/*教会に戻る*/
		else if(map[kx][y]==2 && nokori==0) {
			result++;
			if(house)map[kx][ky]=1;/*通った家を元に戻す*/
			return result;
		}
		/*通れない*/
		else if(map[kx][y]==3)break;
	}
	if(house)map[kx][ky]=1;/*通った家を元に戻す*/
	return result;
}

int main(void) {
	int x,y;
	int kx,ky;
	int kazu;
	while(1) {
		scanf("%d %d",&m,&n);
		if(m==0 && n==0)break;
		kazu=0;
		kx=ky=0;
		/*読み込み*/
		for(y=0;y<n;y++) {
			for(x=0;x<m;x++) {
				scanf("%d",&map[x][y]);
				if(map[x][y]==2) {/*教会*/
					kx=x;
					ky=y;
				} else if(map[x][y]==1)kazu++;/*家*/
			}
		}
		/*計算*/
		printf("%d\n",chousa(kx,ky,kazu));
	}
	return 0;
}