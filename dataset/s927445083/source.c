// AOJ 1319 Driving an Icosahedral Rover
// 2018.2.8 bal4u

#include <stdio.h>
#include <string.h>

//#define getchar_unlocked()  getchar()
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int in()
{
	int n = 0;
	int c = getchar_unlocked();
	if (c == '-') {
		c = getchar_unlocked();
		do n = (n<<3)+(n<<1) + (c & 0xf), c = getchar_unlocked();
		while (c >= '0');
		return -n;
	}
	do n = (n<<3)+(n<<1) + (c & 0xf), c = getchar_unlocked();
	while (c >= '0');
	return n;
}

#define INF  120
#define BASE 100
#define MAX  100
#define LIM	 200
#define QMAX 910000

typedef struct { unsigned char x, y, k; } Q;
Q q[QMAX+2]; int top, end;

int mv[60][3] = {
{ 5, 13, 15},{14, 16,  3},{17,  4, 12},
{20,  8,  1},{ 6,  2, 18},{ 0, 19,  7},
{ 4, 22, 11},{23,  9,  5},{10,  3, 21},
{12,  7, 24},{ 8, 25, 13},{26, 14,  6},
{ 9, 28,  2},{29,  0, 10},{ 1, 11, 27},
{32, 34,  0},{35,  1, 30},{ 2, 31, 33},
{34, 37,  4},{38,  5, 35},{ 3, 33, 36},
{37, 40,  8},{41,  6, 38},{ 7, 36, 39},
{40, 43,  9},{44, 10, 41},{11, 39, 42},
{43, 32, 14},{30, 12, 44},{13, 42, 31},
{28, 46, 16},{47, 17, 29},{15, 27, 45},
{50, 20, 17},{18, 15, 48},{16, 49, 19},
{53, 23, 20},{21, 18, 51},{19, 52, 22},
{56, 26, 23},{24, 21, 54},{22, 55, 25},
{59, 29, 26},{27, 24, 57},{25, 58, 28},
{58, 50, 32},{48, 30, 59},{31, 57, 49},
{46, 53, 34},{51, 35, 47},{33, 45, 52},
{49, 56, 37},{54, 38, 50},{36, 48, 55},
{52, 59, 40},{57, 41, 53},{39, 51, 58},
{55, 47, 43},{45, 44, 56},{42, 54, 46}};

char d[201][201][60];
int dx[2][3] = {{-1,1,0},{-1,1, 0}};
int dy[2][3] = {{ 0,0,1},{ 0,0,-1}};
int dk[2][3] = {{ 1,0,2},{ 0,1, 2}};

int main()
{
	int x, y, k, i, f, nx, ny, nk, ans;

	memset(d, INF, sizeof(d));
	d[BASE][BASE][0] = 0;
	q[0].x = BASE, q[0].y = BASE, q[0].k = 0, top = 0, end = 1;
	while (top != end) {
		x = q[top].x, y = q[top].y, k = q[top++].k;
		if (d[x][y][k] >= MAX) break;

		f = (x+y) & 1;
		for (i = 0; i < 3; i++) {
			nx = x + dx[f][i], ny = y + dy[f][i], nk = mv[k][dk[f][i]];

			if (nx >= 0 && nx <= LIM && ny >= 0 && ny <= LIM && d[x][y][k]+1 < d[nx][ny][nk]) {
				d[nx][ny][nk] = d[x][y][k]+1;
				q[end].x = nx, q[end].y = ny, q[end++].k = nk;
			}
		}
	}

	while (1) {
		x = in(), y = in(), k = in();
		if ((x|y|k) == 0) break;
		x += BASE, y += BASE, k *= 3;
		ans = INF;
		for (i = 0; i < 3; i++) if (ans > d[x][y][k+i]) ans = d[x][y][k+i];
		printf("%d\n", ans);
	}
	return 0;
}

