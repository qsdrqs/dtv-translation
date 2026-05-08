// AOJ 1314 Matrix Calculator
// 2018.2.12 bal4u

#include <stdio.h>
#include <ctype.h>
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

typedef unsigned short USHOT;
#define MAX 32768
#define M   32767
#define SIZE 10

typedef struct { USHOT r, c, a[100][100]; } MAT;
MAT mat[26];
MAT spool[SIZE+1], tmp, ans;
char used[SIZE+1]; int top;
char buf[100], *p;

void expr(MAT *x);

// malloc
int new() {
	int i, k;
	used[k=i=top] = 1;
	while (++i < SIZE) if (!used[i]) { top = i; break; }
	return k;
}

// free
void dis(int k) { used[k] = 0; if (k < top) top = k; }

int in() {
	int n = 0;
	while (isdigit(*p)) n = (n<<3)+(n<<1) + (*p++ & 0xf);
	return n;
}

void add(MAT *a, MAT *b) { int r, c;
	for (r = 0; r < a->r; r++) for (c = 0; c < a->c; c++)
		a->a[r][c] = (a->a[r][c] + b->a[r][c]) & M;
}

void sub(MAT *a, MAT *b) { int r, c;
	for (r = 0; r < a->r; r++) for (c = 0; c < a->c; c++)
		a->a[r][c] = (a->a[r][c] + MAX - b->a[r][c]) & M;
}

void mul(MAT *a, MAT *b) { int r, c, k, i;
	if (a->r ==1 && a->c == 1) {
		k = a->a[0][0];
		a->r = b->r, a->c = b->c;
		for (r = 0; r < b->r; r++) for (c = 0; c < b->c; c++)
			a->a[r][c] = (b->a[r][c] * k) & M;
	} else if (b->r == 1 && b->c == 1) {
		k = b->a[0][0];
		for (r = 0; r < a->r; r++) for (c = 0; c < a->c; c++)
			a->a[r][c] = (a->a[r][c] * k) & M;
	} else {
		memset(&tmp, 0, sizeof(tmp));
		tmp.r = a->r, k = a->c, tmp.c = b->c;
		for (i = 0; i < k; i++) {
			for (r = 0; r < tmp.r; r++) for (c = 0; c < tmp.c; c++)
				tmp.a[r][c] = (tmp.a[r][c] +
				   (((unsigned int)(a->a[r][i]) * (unsigned int)(b->a[i][c])) & M)) & M;
		}
		memcpy(a, &tmp, sizeof(tmp));
	}
}

void row(MAT *x)
{
	int r, c, _t;
	MAT *t;

	expr(x);
	t = spool + (_t = new());
	while (*p == ' ') {
		p++;
		expr(t);
		for (r = 0; r < t->r; r++) for (c = 0; c < t->c; c++)
			x->a[r][c + x->c] = t->a[r][c];
		x->c += t->c;
	}
	dis(_t);
}

void matrix(MAT *x)
{
	int r, c, _t;
	MAT *t;

	p++;
	row(x);
	t = spool + (_t = new());
	while (*p != ']') {
		p++;
		row(t);
		for (r = 0; r < t->r; r++) for (c = 0; c < t->c; c++)
			x->a[x->r + r][c] = t->a[r][c];
		x->r += t->r;
	}
	if (*p != '.') p++;
	dis(_t);
}

void primary(MAT *x)
{
	int r, c, f, _t1, _t2;
	char *q;
	MAT *t1, *t2;

	if (isdigit(*p)) { x->r = x->c = 1, x->a[0][0] = in(); }
	else if (isalpha(*p)) memcpy(x, mat + (*p++ - 'A'), sizeof(MAT));
	else if (*p == '(') p++, expr(x), p++;
	else matrix(x);

	while (1) {
		if (*p == '\'') {
			f = 1, p++;
			while (*p == '\'') p++, f = !f;
			if (f) {
				memcpy(&tmp, x, sizeof(MAT));
				x->r = tmp.c, x->c = tmp.r;
				for (r = 0; r < tmp.r; r++) for (c = 0; c < tmp.c; c++)
					x->a[c][r] = tmp.a[r][c];
			}
		} else if (*p == '(') {
			q = p+1, f = 0;
			while (*q != '.') {
				if (*q == '(') f++;
				else if (*q == ')') f--;
				if (!f && *q == ',') break;
				q++;
			}
			if (*q == '.') break;

			t1 = spool + (_t1=new());
			t2 = spool + (_t2=new());
			p++, expr(t1), p++, expr(t2), p++;
			tmp.r = t1->c, tmp.c = t2->c;
			for (r = 0; r < tmp.r; r++) for (c = 0; c < tmp.c; c++)
				tmp.a[r][c] = x->a[t1->a[0][r]-1][t2->a[0][c]-1];
			memcpy(x, &tmp, sizeof(tmp));
			dis(_t2), dis(_t1);
		} else break;
	}
}

void factor(MAT *x)
{
	int r, c, minus;

	minus = 0; while (*p == '-') p++, minus = !minus;
	primary(x);
	if (minus) {
		for (r = 0; r < x->r; r++) for (c = 0; c < x->c; c++)
			x->a[r][c] = MAX - x->a[r][c];
	}
}

void term(MAT *x)
{
	int _y;
	MAT *y;

	factor(x);
	y = spool + (_y=new());
	while(1) {
		if (*p != '*') break;
		p++;
		factor(y);
		mul(x, y);
	}
	dis(_y);
}

void expr(MAT *x)
{
	int op, _y;
	MAT *y;

	term(x);
	y = spool + (_y=new());
	while(1) {
		if      (*p == '+') op = 1;
		else if (*p == '-') op = 0;
		else break;
		p++;
		term(y);
		if (op) add(x, y);
		else    sub(x, y);
	}
	dis(_y);
}

int main()
{
	int n, r, c, s;

	while (fgets(p=buf, sizeof(buf), stdin) && *p != '0') {
		n = in();
		while (n--) {
			fgets(p=buf, sizeof(buf), stdin);
			s = *p - 'A', p += 2;
			expr(&ans);
			for (r = 0; r < ans.r; r++) {
				printf("%d", ans.a[r][0]);
				for (c = 1; c < ans.c; c++) printf(" %d", ans.a[r][c]);
				putchar('\n');
			}
			memcpy(mat+s, &ans, sizeof(ans));
		}
		puts("-----");
	}
	return 0;
}
