#include <stdio.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main( void ) {
	int i, j, n, data[ 100 ], cnt, tmp;

	for ( ; scanf( "%d", &n ), n; printf( "%d\n", cnt ) ) {
		for ( i = n; i--; scanf( "%d", data + i ) );

		cnt = 0;
		for ( i = 0; i < n - 1; i++ )
			for ( j = n - 1; j > i; j-- )
				if ( data[ j - 1 ] < data[ j ] ) {
					tmp = data[ j - 1 ];
					data[ j - 1 ] = data[ j ];
					data[ j ] = tmp;

					cnt++;
				}
	}

	return 0;
}