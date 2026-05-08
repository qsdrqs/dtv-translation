#include<stdio.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main(void){
    int n,k,x[2][50],y[2][50],d[2][50],a[100],b[100],c[100],i,j,h,m,z,count;
    long long int ans=0LL,surface;
    scanf("%d%d",&n,&k);
    for(i=0; i<n; i++){
        scanf("%d%d%d%d%d%d",&x[0][i],&y[0][i],&d[0][i],&x[1][i],&y[1][i],&d[1][i]);
    }
    for(i=0; i<n; i++){
        for(j=0; j<2; j++){
            a[i*2+j]=x[j][i];
            b[i*2+j]=y[j][i];
            c[i*2+j]=d[j][i];
        }
    }
    n*=2;
    for(i=0; i<n-1; i++){
        for(j=i+1; j<n; j++){
            if(a[i]>a[j]){
                z = a[i];
                a[i] = a[j];
                a[j] = z;
            }
            if(b[i]>b[j]){
                z = b[i];
                b[i] = b[j];
                b[j] = z;
            }
            if(c[i]>c[j]){
                z = c[i];
                c[i] = c[j];
                c[j] = z;
            }
        }
    }
    z = n-1;
    n/=2;
    for(i=0; i<z; i++){
        for(j=0; j<z; j++){
            for(h=0; h<z; h++){
                count=0;
                for(m=0; m<n; m++){
                    if(x[0][m]<=a[i] && x[1][m]>=a[i+1] && y[0][m]<=b[j] && y[1][m]>=b[j+1] && d[0][m]<=c[h] && d[1][m]>=c[h+1]){
                        count++;
                    }
                }
                if(count>=k){
                    surface  = (a[i+1]-a[i]);
                    surface *= (b[j+1]-b[j]);
                    surface *= (c[h+1]-c[h]);
                    ans += surface;
                }
            }
        }
    }
    printf("%lld\n",ans);
    return 0;
}