// AOJ 1054: Distorted Love
// 2017.9.28 bal4u@uu

#include <stdio.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { int x1, y1, x2, y2; char nm[25]; int pag; } BTN;
typedef struct { char nm[25]; int bn; BTN btn[102]; } PAG;
PAG pag[200]; int n;
int buf[2000], size;
int now;

int whatPage(char *nm)
{
	int i;
	for (i = 0; i < n; i++) if (strcmp(nm, pag[i].nm) == 0) return i;
	while (1);   // panic
	return -1;
}

int main()
{
	int h, w, m, i, j, k, x, y;
	PAG *pp;
	char cmd[20];

	while (scanf("%d", &n) && n > 0) {
		scanf("%d%d", &w, &h);
		for (pp = pag, i = 0; i < n; i++, pp++) {
			scanf("%s%d", pp->nm, &k), pp->bn = k;
			for (j = 0; j < k; j++)
				scanf("%d%d%d%d%s", &pp->btn[j].x1, &pp->btn[j].y1,
					  &pp->btn[j].x2, &pp->btn[j].y2, &pp->btn[j].nm);
		}
		for (pp = pag, i = 0; i < n; i++, pp++)
			for (j = 0; j < pp->bn; j++) pp->btn[j].pag = whatPage(pp->btn[j].nm);

		now = 0, buf[0] = 0, size = 1;
		scanf("%d", &m);
		while (m-- > 0) {
			scanf("%s", cmd);
			if (*cmd == 'b') {
				if (now > 0) now--;
			} else if (*cmd == 'f') {
				if (now < size-1) now++;
			} else if (*cmd == 's') puts(pag[buf[now]].nm);
			else {		// click
				scanf("%d%d", &x, &y);
				pp = pag + buf[now];
				for (j = 0; j < pp->bn; j++) {
					if (pp->btn[j].x1 <= x && x <= pp->btn[j].x2 &&
						pp->btn[j].y1 <= y && y <= pp->btn[j].y2) {
						buf[++now] = pp->btn[j].pag;
						size = now+1;
						break;
					}
				}
			}
		}
	}
	return 0;
}