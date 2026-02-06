#include <stdio.h>

int singleFunction(int x) {
    return x + 1;
}

int main(void) {
    int x = 0;
    if (scanf("%d", &x) != 1) {
        return 1;
    }
    printf("%d\n", singleFunction(x));
    return 0;
}
