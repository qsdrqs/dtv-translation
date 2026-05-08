// Aizu 1157: Roll-A-Big-Ball
// 2017.9.15 bal4u@uu

#include <stdio.h>
#include <math.h>

#define INF 1e8

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { long long x, y; } PP;
typedef struct { long long x[5], y[5], h; } BK;
BK blk[52];
PP sg[2];

int isPointonSegment(long long x, long long y, long long x1, long long y1, long long x2, long long y2)
{
    long long d;
    if (x1 > x2) d = x1, x1 = x2, x2 = d;
    if (y1 > y2) d = y1, y1 = y2, y2 = d;
    return (x1 <= x && x <= x2 && y1 <= y && y <= y2 &&
           (y-y1)*(x2-x1) == (y2-y1)*(x-x1));
}

int crossSegments(long long x11, long long y11, long long x12, long long y12,
                  long long x21, long long y21, long long x22, long long y22)
{
    long long s11, s12, s21, s22;
    int r = 0;

    s11 = (x22-x21) * (y11-y21) + (y22-y21) * (x21-x11);
    s12 = (x22-x21) * (y12-y21) + (y22-y21) * (x21-x12);
    s21 = (x12-x11) * (y21-y11) + (y12-y11) * (x11-x21);
    s22 = (x12-x11) * (y22-y11) + (y12-y11) * (x11-x22);
    if      (s11 == 0) { if (r == 0) r = isPointonSegment(x11, y11, x21, y21, x22, y22);}
    else if (s12 == 0) { if (r == 0) r = isPointonSegment(x12, y12, x21, y21, x22, y22);}
    else if (s21 == 0) { if (r == 0) r = isPointonSegment(x21, y21, x11, y11, x12, y12);}
    else if (s22 == 0) { if (r == 0) r = isPointonSegment(x22, y22, x11, y11, x12, y12);}
    else {
        r = ((s11 <= 0 && s12 >= 0) || (s11 >= 0 && s12 <= 0)) &&
            ((s21 <= 0 && s22 >= 0) || (s21 >= 0 && s22 <= 0));
    }
    return r;
}

int insidePolygon(long long x, long long y, long long *xx, long long *yy)
{
	long long i, j, k;
	long long sa, sb;

	k = 0;
	for (i = 1, j = 2; j < 4; i++, j++) {
	    sa = (xx[i]-xx[k]) * (y    -yy[k]) + (yy[i]-yy[k]) * (xx[k]-x    );
		sb = (xx[i]-xx[k]) * (yy[j]-yy[k]) + (yy[i]-yy[k]) * (xx[k]-xx[j]);
		if (sa*sb <= 0) continue;

		sa = (xx[j]-xx[i]) * (y    -yy[i]) + (yy[j]-yy[i]) * (xx[i]-x    );
		sb = (xx[j]-xx[i]) * (yy[k]-yy[i]) + (yy[j]-yy[i]) * (xx[i]-xx[k]);
		if (sa*sb <= 0) continue;

	    sa = (xx[k]-xx[j]) * (y    -yy[j]) + (yy[k]-yy[j]) * (xx[j]-x    );
		sb = (xx[k]-xx[j]) * (yy[i]-yy[j]) + (yy[k]-yy[j]) * (xx[j]-xx[i]);
		if (sa*sb <= 0) continue;
	    return 1;
	}
	return 0;
}

double point2point(long long x1, long long y1, long long x2, long long y2)
{
	long long dx, dy;

	dx = x2 - x1, dy = y2 - y1;
	return sqrt((double)(dx * dx + dy * dy));
}

double point2line(long long x, long long y, long long sx, long long sy,
				  long long ex, long long ey, int *onseg)
{
   long long us, ub;
   double xx, yy;
 
   us = ( x - sx) * (ex - sx) + ( y - sy) * (ey - sy);
   ub = (ex - sx) * (ex - sx) + (ey - sy) * (ey - sy);
 
   /* closest point falls within the line segment */
   *onseg = (us >= 0 && us <= ub);

   if      (us == 0)  xx = (double)sx, yy = (double)sy; 
   else if (us == ub) xx = (double)ex, yy = (double)ey;
   else {
      xx = sx + (ex - sx) * (double)us / (double)ub;
      yy = sy + (ey - sy) * (double)us / (double)ub;
   }
   return sqrt((x - xx)*(x - xx) + (y - yy)*(y - yy));
}

int main()
{
	int n, i, j, k, onseg;
	double dist, t, r, ans;

	while (scanf("%d", &n) && n) {
		scanf("%lld%lld%lld%lld", &sg[0].x, &sg[0].y, &sg[1].x, &sg[1].y);
		for (i = 0; i < n; i++) {
			long long x1, y1, x2, y2;
			scanf("%lld%lld%lld%lld%lld", &x1, &y1, &x2, &y2, &blk[i].h);
			blk[i].x[0] = x1, blk[i].y[0] = y1,	blk[i].x[1] = x2, blk[i].y[1] = y1,
			blk[i].x[2] = x2, blk[i].y[2] = y2, blk[i].x[3] = x1, blk[i].y[3] = y2,
			blk[i].x[4] = x1, blk[i].y[4] = y1;
		}
		ans = INF;
		for (i = 0; i < n; i++) {
			dist = INF;
			for (j = 0; j < 4; j++)
				if (crossSegments(sg[0].x, sg[0].y, sg[1].x, sg[1].y, 
					blk[i].x[j], blk[i].y[j], blk[i].x[j+1], blk[i].y[j+1])) goto NG;
			for (k = 0; k < 2; k++)
				if (insidePolygon(sg[k].x, sg[k].y, blk[i].x, blk[i].y)) goto NG;

			for (k = 0; k < 2; k++) for (j = 0; j < 4; j++) {
				t = point2line(sg[k].x, sg[k].y,
					blk[i].x[j], blk[i].y[j], blk[i].x[j+1], blk[i].y[j+1], &onseg);
				if (onseg && t < dist) dist = t;
			}
			for (j = 0; j < 4; j++) {
				t = point2line(blk[i].x[j], blk[i].y[j], sg[0].x, sg[0].y, sg[1].x, sg[1].y, &onseg);
				if (onseg && t < dist) dist = t;
			}
			for (k = 0; k < 2; k++) for (j = 0; j < 4; j++) {
				t = point2point(sg[k].x, sg[k].y, blk[i].x[j], blk[i].y[j]);
				if (t < dist) dist = t;
			}
			if (dist <= blk[i].h) r = dist;
			else r = (blk[i].h*blk[i].h + dist*dist)/(2*blk[i].h);
			if (r < ans) ans = r;
		}
		printf("%.8lf\n", ans);
		continue;
NG:		puts("0");
	}
	return 0;
}