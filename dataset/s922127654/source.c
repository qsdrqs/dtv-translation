// AOJ 2820 Binary Sequence
// 2018.3.22 bal4u

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

//// 高速数値入出力
#if 1
#define gc() getchar_unlocked()
#define pc(c) putchar_unlocked(c)
#else
#define gc() getchar()
#define pc(c) putchar(c)
#endif
// 非負整数の入力
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
	int n = 0, c = gc();
	do n = 10 * n + (c & 0xf), c = gc(); while (c >= '0');
	return n;
}

// 文字列の入力　スペース以下の文字で入力終了
void ins(char *s)
{
	do *s = gc();
	while (*s++ > ' ');
	*(s - 1) = 0;
}

// 非負整数の表示、最後改行あり
void out(int n)
{
	int i;
	char ob[20];

	if (!n) pc('0');
	else {
		//		if (n < 0) pc('-'), n = -n;
		i = 0; while (n) ob[i++] = n % 10 + '0', n /= 10;
		while (i--) pc(ob[i]);
	}
	pc('\n');
}

// 空間の併合・分割（木構造ではない）
#define MAX 100005
typedef struct { int a, b; } B;
B data[MAX]; int BN;

void b_init()
{
	BN = 2, data[0].a = data[0].b = -1, data[1].a = data[1].b = MAX;
}

// バイナリサーチ
int bsch(int x)
{
	int m, l = 0, r = BN;
	while (l < r) {
		m = (l + r) >> 1;
		if (data[m].a == x) return m;
		if (data[m].a < x) l = m + 1; else r = m;
	}
	return l - 1;
}

// ブロック移動（木構造にすればもっと高速になるのに）
static void insert(int l, int r, int a, int b)
{
	if (r < l) memmove(data + l + 1, data + l, sizeof(B)*(BN - l)), BN++;
	else if (l < r) memmove(data + l, data + r, sizeof(B)*(BN - r)), BN -= r - l;
	data[l].a = a, data[l].b = b;
}

static void delete(int l, int r)
{
	if (r < l) return;
	memmove(data + l, data + r + 1, sizeof(B)*(BN - (r + 1)));
	BN -= r-l+1;
}
// 空間の登録
void update(int mode, int a, int b)
{
	int l = bsch(a), r = bsch(b);
	if (mode) {
		if (b <= data[l].b) return;
		if (data[l].b < a && data[l].b + 1 != a) l++; else a = data[l].a;
		if (b < data[r].b) b = data[r].b;
		if (data[r + 1].a == b + 1) b = data[++r].b;
		insert(l, r, a, b);
	}
	else {
		if (l == r) {
			if (data[l].a == a) {
				if (data[l].b <= b) delete(l, l);
				else data[l].a = b + 1;
			}
			else if (b < data[l].b) {
				memmove(data+l+2, data+l+1, sizeof(B)*(BN-l-1)), BN++;
				data[l+1].a = b+1, data[l+1].b = data[l].b;
				data[l].b = a-1;
			} else if (a <= data[l].b) data[l].b = a - 1;
		}
		else {
			if (data[l].a == a) ;
			else {
				if (a <= data[l].b) data[l].b = a - 1;
				l++;
			}

			if (b < data[r].b) data[r].a = b + 1, r--;
			delete(l, r);
		}
	}
}

// 離れた空間の数
int query() { return BN - 2; }


// 本問題関連
char x[MAX]; int N;

int main()
{
	int i, ii, Q, l, r, b;

	// 入力受付
	N = in(), ins(x+1);
	
	// 連続する'1'の空間登録
	b_init();     // 初期化
	ii = 0; for (i = 1; i <= N; i++) {
		if (x[i] & 1) {
			if (!ii) ii = i;
		}
		else {
			if (ii) update(1, ii, i - 1), ii = 0;
		}
	}
	if (ii) update(1, ii, i - 1);

	Q = in(); while (Q--) {
		l = in(), r = in(), b = gc(), gc();
		if (l > r) update(b & 1, r, l);
		else       update(b & 1, l, r);
		out(query());
	}
	return 0;
}

