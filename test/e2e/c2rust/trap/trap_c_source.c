#include <stdio.h>
#include <stdlib.h>

int trap(int *height, int heightSize) {
    if (heightSize < 3) return 0;          // need at least 3 bars to hold water

    int left  = 0;                         // left scan pointer
    int right = heightSize - 1;            // right scan pointer
    int left_max  = 0;                     // highest bar seen from the left so far
    int right_max = 0;                     // highest bar seen from the right so far
    int water = 0;                         // accumulated answer

    while (left < right) {
        if (height[left] < height[right]) {
            // The left side is the bottleneck
            if (height[left] >= left_max)
                left_max = height[left];   // update tallest left wall
            else
                water += left_max - height[left];   // fill water up to left_max
            ++left;
        } else {
            // The right side is the bottleneck
            if (height[right] >= right_max)
                right_max = height[right]; // update tallest right wall
            else
                water += right_max - height[right]; // fill water up to right_max
            --right;
        }
    }
    return water;
}

int main(void) {
    int n = 0;
    if (scanf("%d", &n) != 1) {
        return 1;
    }
    if (n < 0) {
        return 1;
    }
    int *arr = NULL;
    if (n > 0) {
        arr = (int *)malloc(sizeof(int) * (size_t)n);
        if (!arr) {
            return 1;
        }
        for (int i = 0; i < n; i++) {
            if (scanf("%d", &arr[i]) != 1) {
                free(arr);
                return 1;
            }
        }
    }
    int result = trap(arr, n);
    printf("%d\n", result);
    free(arr);
    return 0;
}
