use std::io;

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
            // The left side is the bottleneck
            if height[left] >= left_max {
                left_max = height[left];
            } else {
                water += left_max - height[left];
            }
            left += 1;
        } else {
            // The right side is the bottleneck
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
    let mut n: i32 = 0;
    let mut input = String::new();
    
    // Read the first integer (n)
    match io::stdin().read_line(&mut input) {
        Ok(_) => {
            if let Ok(n_val) = input.trim().parse::<i32>() {
                n = n_val;
            } else {
                println!("Error: invalid input");
                return;
            }
        }
        Err(_) => {
            println!("Error: failed to read input");
            return;
        }
    }

    if n < 0 {
        println!("Error: n must be non-negative");
        return;
    }

    let mut height: Vec<i32> = Vec::new();

    if n > 0 {
        // Read n integers
        let mut input = String::new();
        match io::stdin().read_line(&mut input) {
            Ok(_) => {
                let values: Vec<i32> = input
                    .trim()
                    .split_whitespace()
                    .map(|s| s.parse::<i32>().unwrap_or(0))
                    .collect();
                
                if values.len() != n as usize {
                    println!("Error: expected {} values", n);
                    return;
                }
                
                height = values;
            }
            Err(_) => {
                println!("Error: failed to read values");
                return;
            }
        }
    }

    let result = trap(&height);
    println!("{}", result);
}
