#include <stdio.h>
#include <math.h>

#define PI 3.1415926535897932384626433832795028841
#define EPS (1e-10)

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
	double R;
	while(scanf("%lf",&R)==1 && R>0.0) {
		int bunbo,bunsi1,bunsi2;
		double g1,g2;
		for(bunbo=1;bunbo<=100000000;bunbo++) {
			bunsi1=(int)(PI*bunbo);
			bunsi2=bunsi1+1;
			g1=fabs((double)bunsi1/bunbo-PI);
			g2=fabs((double)bunsi2/bunbo-PI);
			if(g1<R+EPS ||g2<R+EPS)break;
		}
		printf("%d/%d\n",g1<=g2?bunsi1:bunsi2,bunbo);
	}
	return 0;
}