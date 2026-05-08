#include <stdio.h>
#define N 10000

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
  int i, j;
  int n;
  
  int map[ N + 1 ];

  map[ 0 ] = map[ 1 ] = 0;
  for( i = 2; i <= N; i++ )
    map[ i ] = 1;
  for( i = 2; i < N; i++ )
    for( j = i * 2; j < N; j += i )
      map[ j ] = 0;

  while( scanf( "%d", &n ) != EOF ) {
    int count = 0;

    for( i = 1; i <= n; i++ )
      if( map[ i ] && map[ n - i + 1 ] )
        count++;

    printf( "%d\n", count );
  }

  return( 0 );
}