// AOJ 2301: Sleeping Time
// 2017.10.7 bal4u@uu

#include <stdio.h>
#include <math.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

double p, e, t;

double combi(int k, double l, double r)
{
    double m = (l+r)/2.0;
    if (k == 0) return fabs(m-t) < e ? 1.0 : 0;
    if (l+e < t || t < r-e) return 0;
    if (l-e < t && t < r+e) return 1.0;
    if ((l+r)/2.0 >= t) return p*combi(k-1, m, r) + (1.0-p)*combi(k-1, l, m);
    else                return p*combi(k-1, l, m) + (1.0-p)*combi(k-1, m, r);
}
  
int main()
{
	int k, r, l;

	scanf("%d%d%d%lf%lf%lf", &k, &r, &l, &p, &e, &t);
	p = 1 - p;
	printf("%lf\n", combi(k, l, r));
	return 0;
}