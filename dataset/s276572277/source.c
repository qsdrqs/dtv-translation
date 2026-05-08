// AOJ 2210: Star Watching
// 2017.10.1

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define PI 3.1415926535897932384626433832795
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

double xpol, ypol, zpol;			// Polaris
double aa;

int check(double a, double h)
{
	double theta, phi;
	double x, y, z, zz;

	theta = (180 - a) * PI/180.0;
	phi = h * PI/180.0;
	x = cos(theta)*cos(phi);
	y = sin(theta)*cos(phi);
	z = sin(phi);

	zz =  (zpol*xpol*(1-cos(aa)) - ypol*sin(aa))*x
		+ (ypol*zpol*(1-cos(aa)) + xpol*sin(aa))*y
		+ (zpol*zpol*(1-cos(aa)) +      cos(aa))*z;

	return zz > 0;
}

int main()
{
	int t, n, m, mm, dd, hh, min, i, j, f;
	double a, h;
	char date[20], time[20], name[52], *p;
	int mdays[13] = {0,31,29,31,30,31,30,31,31,30,31,30,31};

	a = PI, h = 43.2*PI/180.0;		// Polaris
	xpol = cos(a)*cos(h);
	ypol = sin(a)*cos(h);
	zpol = sin(h);

	scanf("%d", &t);
	while (t-- > 0) {
		scanf("%s%s", date, time);
		p = date; mm = atoi(p); while (*p != '/') p++;
		p++;      dd = atoi(p);
		p = time; hh = atoi(p); while (*p != ':') p++;
		p++;     min = atoi(p);
		for (i = 1; i < mm; i++) dd += mdays[i];
		min += 60 * (24*(dd-1) + hh);
		aa = -(double)min * (1+1/365.24)*PI*2/1440.0;

		scanf("%d", &n);
		for (i = 0; i < n; i++) {
			scanf("%s%d", name, &m);
			for (f = 1, j = 0; j < m; j++) {
				scanf("%lf%lf", &a, &h);
				if (f && !check(a, h)) f = 0;
			}
			if (f) puts(name);
		}
	}
	return 0;
}