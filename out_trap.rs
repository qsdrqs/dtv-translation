use std::io::{self, Read};

fn trap(height: &[i32]) -> i32 {
    if height.len() < 3 {
        return 0;
    }

    let mut left = 0;
    let mut right = height.len() - 1;
    let mut left_max = 0;
    let mut right_max = 0;
    let mut water = 0;

    while left < right {
        if height[left] < height[right] {
            // Left side is the bottleneck
            if height[left] >= left_max {
                left_max = height[left];
            } else {
                water += left_max - height[left];
            }
            left += 1;
        } else {
            // Right side is the bottleneck
            if height[right] >= right_max {
                right_max = height[right];
            } else {
                water += right_max - height[right];
            }
            right -= 1;
        }
    }

    water
}

fn main() {
    let mut input = String::new();
    io::stdin().read_line(&mut input).expect("Failed to read input");

    let n: i32 = input
        .trim()
        .parse()
        .expect("Invalid input: expected a non-negative integer");

    if n < 0 {
        println!("1");
        return;
    }

    if n == 0 {
        println!("0");
        return;
    }

    let mut height: Vec<i32> = Vec::with_capacity(n as usize);

    let mut input_line = String::new();
    io::stdin().read_line(&mut input_line).expect("Failed to read input");

    let values: Vec<i32> = input_line
        .trim()
        .split_whitespace()
        .map(|s| s.parse::<i32>().expect("Invalid integer"))
        .collect();

    if values.len() != n as usize {
        println!("1");
        return;
    }

    let result = trap(&values);
    println!("{}", result);
}
