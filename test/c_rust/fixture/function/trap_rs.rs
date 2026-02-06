use std::io::{self, Read};

fn trap(height: &[i32]) -> i32 {
    let n = height.len();
    if n < 3 {
        return 0;
    }

    let mut left: usize = 0;
    let mut right: usize = n - 1;
    let mut left_max: i32 = 0;
    let mut right_max: i32 = 0;
    let mut water: i32 = 0;

    while left < right {
        if height[left] < height[right] {
            if height[left] >= left_max {
                left_max = height[left];
            } else {
                water += left_max - height[left];
            }
            left += 1;
        } else {
            if height[right] >= right_max {
                right_max = height[right];
            } else {
                water += right_max - height[right];
            }
            if right == 0 {
                break;
            }
            right -= 1;
        }
    }

    water
}
