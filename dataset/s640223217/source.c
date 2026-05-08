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

int main(void) {
	int n,m,bib[128] = {0},swh,i,j;
	scanf("%d%d",&n,&m);
	for(i = 1;i <= n;i++){scanf("%d",&bib[i]);}
	for(i = 1;i <= m;i++){
		for(j = 1;j < n;j++){
			if(bib[j] % i > bib[j+1] % i){
				swh = bib[j];
				bib[j] = bib[j+1];
				bib[j+1] = swh;
			}
		}
	}
	for(i = 1;i <= n;i++){
		printf("%d\n",bib[i]);
	}
	return 0;
}