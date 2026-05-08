#include <stdio.h>

#define WIDTH_MAX 30
#define HEIGHT_MAX 30

#define next( i ) ( ( ( i ) + 1 ) % ( WIDTH_MAX * HEIGHT_MAX ) )

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct {
	int type;
	int min;
} FIELD;

FIELD field[ WIDTH_MAX * 2 + 1 ][ HEIGHT_MAX * 2 + 1 ] = {};
const int dx[ 4 ] = { -1, 0, 1, 0 }, dy[ 4 ] = { 0, -1, 0, 1 };

int queue[ WIDTH_MAX * HEIGHT_MAX ], front, rear;

int bfs( int, int );

int main( void ) {
	int x, y, w, h;

	for ( x = 1; x <= WIDTH_MAX * 2 - 1; x += 2 )
		field[ x ][ 0 ].type = 1;
	for ( y = 1; y <= HEIGHT_MAX * 2 - 1; y += 2 )
		field[ 0 ][ y ].type = 1;

	for ( ; scanf( "%d %d", &w, &h ), w; printf( "%d\n", bfs( w, h ) ) ) {
		for ( y = 1; y <= h * 2 - 1; y += 2 )
			for ( x = 1; x <= w * 2 - 1; x += 2 )
				field[ x ][ y ].min = 0;
		for ( x = 1; x <= w * 2 - 1; x += 2 )
			field[ x ][ h * 2 ].type = 1;
		for ( y = 1; y <= h * 2 - 1; y += 2 )
			field[ w * 2 ][ y ].type = 1;

		for ( y = 1; y <= h * 2 - 1; y++ )
			for ( x = y % 2 + 1; x <= w * 2 - 1 ; x += 2 )
				scanf( "%d", &field[ x ][ y ].type );
	}

	return 0;
}

int bfs( int w, int h ) {
	int i, x, y, tmp;

	front = rear = 0;

	queue[ rear ] = h * 2 + 2;
	rear = next( rear );

	field[ 1 ][ 1 ].min = 1;

	while ( rear != front ) {
		tmp = queue[ front ];
		front = next( front );

		x = tmp / ( h * 2 + 1 );
		y = tmp % ( h * 2 + 1 );

		if ( x == w * 2 - 1 && y == h * 2 - 1 )
			break;

		for ( i = 4; i--;  ) {
			int nx1 = x + dx[ i ], ny1 = y + dy[ i ], nx2 = nx1 + dx[ i ], ny2 = ny1 + dy[ i ];

			if ( !field[ nx1 ][ ny1 ].type && !field[ nx2 ][ ny2 ].min ) {
				queue[ rear ] = nx2 * ( h * 2 + 1 ) + ny2;
				rear = next( rear );

				field[ nx2 ][ ny2 ].min = field[ x ][ y ].min + 1;
			}
		}
	}

	return field[ w * 2 - 1 ][ h * 2 - 1 ].min;
}