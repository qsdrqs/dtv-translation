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
            right -= 1;
        }
    }

    water
}

fn main() {
    let mut input = String::new();
    std::io::stdin().read_line(&mut input).unwrap();

    let n: i32 = input
        .trim()
        .parse()
        .expect("Invalid input: expected a valid integer for n");

    if n < 0 {
        println!("1");
        return;
    }

    let mut height: Vec<i32> = Vec::new();

    if n > 0 {
        let mut input_line = String::new();
        std::io::stdin().read_line(&mut input_line).unwrap();

        let values: Vec<i32> = input_line
            .trim()
            .split_whitespace()
            .map(|s| s.parse::<i32>().unwrap())
            .collect();

        if values.len() != n as usize {
            println!("1");
            return;
        }

        height = values;
    }

    let result = trap(&height);
    println!("{}", result);
}
