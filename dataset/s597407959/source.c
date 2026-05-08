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
	int m,n;
	while(scanf("%d%d",&m,&n)==2 && (m!=0 || n!=0)) {
		static const char *tani[18] = {
			"", "Man", "Oku", "Cho", "Kei", "Gai", "Jo", "Jou", "Ko", "Kan",
			"Sei", "Sai", "Gok", "Ggs", "Asg", "Nyt", "Fks", "Mts"
		};
		int keisan[18]={1};
		int i;
		for(i=0;i<n;i++) {
			int carry=0;
			int j;
			for(j=0;j<18;j++) {
				keisan[j]=keisan[j]*m+carry;
				carry=keisan[j]/10000;
				keisan[j]%=10000;
			}
		}
		for(i=17;i>=0;i--) {
			if(keisan[i]>0)printf("%d%s",keisan[i],tani[i]);
		}
		putchar('\n');
	}
	return 0;
}