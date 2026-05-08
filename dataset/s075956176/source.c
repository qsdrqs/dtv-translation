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

int main(void)
{
   
int n[26] = {0};
char m[1300];
int i, z;
   
while(1){
   
if(scanf("%s",&m) == EOF)
break;
   
i = 0;
while(1){
if(m[i] == '\0')
break;
   
if('a' <= m[i] && m[i] <= 'z')
n[ m[i] - 'a']++;
   
if('A' <= m[i] && m[i] <= 'Z')
n[ m[i] - 'A']++;
   
i++;
}
}
   
for(i = 0; i < 26; i++){
z = i + 'a';
printf("%c : %d\n", z, n[i]);
}
   
return 0;
}