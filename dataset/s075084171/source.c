// AOJ 2327: Sky Jump
// 2017.12.13 bal4u@uu

#include <stdio.h>

#define G  9.8
#define G2 4.9

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int x[1001], y[1001]; int n;
char buf[15], *p;

int getint()
{
	int n = 0;
	if (*p == '-') {
		p++; while (*p >= '0') n = (n<<3) + (n<<1) + (*p++ & 0xf);
		p++; return -n;
	}
	while (*p >= '0') n = (n<<3) + (n<<1) + (*p++ & 0xf);
	p++; return n;
}

double xcalc(double xx)
{
	int i;
    double t, r = 0;
    for (i = 0; i < n; i++) {
        t = (xx*x[i] + y[i])/G;
        if (t > 0) r += t*x[i];
    }
    return r;
}

double ycalc(double xx)
{
	int i;
	double t, r = 0;
	for (i = 0; i < n; i++) {
		t = (xx*x[i] + y[i])/G;
		if (t > 0) r += (y[i] - G2*t)*t;
	}
	return r;
}

double calc(int x)
{
	double l = -1001, r = 1001, m;
	while (l + 1e-8 < r){
		m = (l + r)/2;
		if (xcalc(m) >= x) r = m; else l = m;
	}
	return ycalc(l);
}

int main()
{
	int X, Y, i;
	double min, max;

	while (fgets(p=buf, 10, stdin) && *p != '0') {
		n = getint();

		for (i = 0; i < n; i++) {
			fgets(p=buf, 15, stdin);
			x[i] = getint(), y[i] = getint();
		}
		fgets(p=buf, 15, stdin);
		X = getint(), Y = getint();

		min = 1e8;
		for (i = 0; i < n; i++) {
			double s = (double)X/x[i], t = (y[i] - G2*s)*s;
			if (t < min) min = t;
		}
		max = calc(X);
	
		if (min <= Y && Y <= max) puts("Yes");
		else puts("No");
	}
	return 0;
}