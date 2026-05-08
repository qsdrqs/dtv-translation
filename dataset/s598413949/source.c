#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>
#include <limits.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int sort(const void *a, const void *b){
    return strcmp((char*)a ,(char*)b);
}

int main(void){
    int n,maxa=1,mina=1,maxz=1,minz=1;
    scanf("%d",&n);
    char s[n][25],t[25],u[n][25];
    for (int i=0; i<n; i++){
        scanf("%s",s[i]);
    }
    scanf("%s",t);
    for (int i=0; i<n; i++){
        strcpy(u[i],s[i]);
        for (int j=0; j<strlen(u[i]); j++){
            if (u[i][j]=='?'){
                u[i][j]='a';
            }
        }
    }
    qsort ((void*)u,n,sizeof(u[0]),sort);
    for (int i=0; i<n; i++){
        if (strcmp(u[i],t)<0){
            mina++;
        }
        if (strcmp(u[i],t)<=0){
            maxa++;
        }
    }
    for (int i=0; i<n; i++){
        strcpy(u[i],s[i]);
        for (int j=0; j<strlen(u[i]); j++){
            if (u[i][j]=='?'){
                u[i][j]='z';
            }
        }
    }
    qsort ((void*)u,n,sizeof(u[0]),sort);
    for (int i=0; i<n; i++){
        if (strcmp(u[i],t)<0){
            minz++;
        }
        if (strcmp(u[i],t)<=0){
            maxz++;
        }
    }
    for (int i=fmin(mina,minz); i<=fmax(maxa,maxz); i++){
        printf("%d",i);
        if (i!=fmax(maxa,maxz)){
            printf(" ");
        }
    }
    printf("\n");
	return 0 ;
}