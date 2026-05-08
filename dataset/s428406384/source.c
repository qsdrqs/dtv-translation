#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// 内部定数
#define D_MOD			1000000007								// 除数(10の9乗+7)
#define D_ARRAY_MAX		105										// 最大配列数
#define D_VAL_MAX		256										// 最大値
#define D_FACT_MAX		D_ARRAY_MAX								// 最大階乗数

// 内部変数
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

static FILE *szpFpI;											// 入力
static int si3PCnt[D_ARRAY_MAX][D_VAL_MAX][D_ARRAY_MAX];		// パターン数[桁数][値][長さ]
static int si1ModFact[D_FACT_MAX];								// 階乗リスト

// 内部変数 - テスト用
#ifdef D_TEST
	static int siRes;
	static FILE *szpFpA;
	static int siTNo;
#endif

// １行出力
int
fOutLine(
	char *pcpLine				// <I> １行
)
{
	char lc1Buf[1024];

#ifdef D_TEST
	lc1Buf[0] = '\0';
	fgets(lc1Buf, sizeof(lc1Buf), szpFpA);
	if (strcmp(lc1Buf, pcpLine)) {
		siRes = -1;
	}
#else
	printf("%s", pcpLine);
#endif

	return 0;
}

// 和 - 取得
int
fGetModSum(
	int piVal1					// <I> 値１
	, int piVal2				// <I> 値２
)
{
	return (piVal1 + piVal2) % D_MOD;
}

// 積 - 取得
int
fGetModMulti(
	int piVal1					// <I> 値１
	, int piVal2				// <I> 値２
)
{
	return (int)((long long)piVal1 * (long long)piVal2 % D_MOD);
}

// 階乗リスト - 作成
int
fMakeModFact(
	int piMax					// <I> 最大値
)
{
	int i;

	si1ModFact[0] = 1;
	si1ModFact[1] = 1;
	for (i = 2; i <= piMax; i++) {
		si1ModFact[i] = fGetModMulti(si1ModFact[i - 1], i);
	}

	return 0;
}

// 実行メイン
int
fMain(
)
{
	int i, j, k;
	char lc1Buf[1024];

	// データ - 初期化
	memset(si3PCnt, 0, sizeof(si3PCnt));
	si3PCnt[0][0][0] = 1;

	// 配列数・k - 取得
	int liACnt, liK;
	fgets(lc1Buf, sizeof(lc1Buf), szpFpI);
	sscanf(lc1Buf, "%d%d", &liACnt, &liK);

	// 配列 - 取得
	for (i = 0; i < liACnt; i++) {
		int liVal;
		fscanf(szpFpI, "%d", &liVal);

		// 現在値でループ
		for (j = 0; j < D_VAL_MAX; j++) {
			int liXor = j ^ liVal;
			for (k = 0; k <= i; k++) {

				// 値 - 追加
				si3PCnt[i + 1][liXor][k + 1] = fGetModSum(si3PCnt[i + 1][liXor][k + 1], si3PCnt[i][j][k]);

				// 値 - 追加しない
				si3PCnt[i + 1][j][k] = fGetModSum(si3PCnt[i + 1][j][k], si3PCnt[i][j][k]);
			}
		}
	}
	fgets(lc1Buf, sizeof(lc1Buf), szpFpI);

	// 階乗リスト - 作成
	fMakeModFact(liACnt);

	// 合計 - 取得
	int liSum = 0;
	for (i = 0; i <= liACnt; i++) {
		int liCnt = fGetModMulti(si3PCnt[liACnt][liK][i], si1ModFact[i]);
		liSum = fGetModSum(liSum, liCnt);
	}

	return liSum;
}

// １回実行
int
fOne(
)
{
	int liRet;
	char lc1Buf[1024];

	// 入力 - セット
#ifdef D_TEST
	sprintf(lc1Buf, ".\\Test\\T%d.txt", siTNo);
	szpFpI = fopen(lc1Buf, "r");
	sprintf(lc1Buf, ".\\Test\\A%d.txt", siTNo);
	szpFpA = fopen(lc1Buf, "r");
	siRes = 0;
#else
	szpFpI = stdin;
#endif

	// 実行メイン
	liRet = fMain();

	// 出力
	sprintf(lc1Buf, "%d\n", liRet);
	fOutLine(lc1Buf);

	// 残データ有無
#ifdef D_TEST
	lc1Buf[0] = '\0';
	fgets(lc1Buf, sizeof(lc1Buf), szpFpA);
	if (strcmp(lc1Buf, "")) {
		siRes = -1;
	}
#endif

	// テストファイルクローズ
#ifdef D_TEST
	fclose(szpFpI);
	fclose(szpFpA);
#endif

	// テスト結果
#ifdef D_TEST
	if (siRes == 0) {
		printf("OK %d\n", siTNo);
	}
	else {
		printf("NG %d\n", siTNo);
	}
#endif

	return 0;
}

// プログラム開始
int
main()
{

#ifdef D_TEST
	int i;
	for (i = D_TEST_SNO; i <= D_TEST_ENO; i++) {
		siTNo = i;
		fOne();
	}
#else
	fOne();
#endif

	return 0;
}

