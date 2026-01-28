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

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();

    let mut it = input.split_whitespace();

    let n_opt = it.next();
    if n_opt.is_none() {
        std::process::exit(1);
    }
    let n_i64: i64 = match n_opt.unwrap().parse() {
        Ok(v) => v,
        Err(_) => std::process::exit(1),
    };
    if n_i64 < 0 {
        std::process::exit(1);
    }
    let n: usize = n_i64 as usize;

    let mut arr: Vec<i32> = Vec::with_capacity(n);
    for _ in 0..n {
        let tok = it.next().unwrap_or_else(|| std::process::exit(1));
        let v: i32 = tok.parse().unwrap_or_else(|_| std::process::exit(1));
        arr.push(v);
    }

    let result = trap(&arr);
    println!("{result}");
}
