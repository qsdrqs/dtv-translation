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
    let mut n: usize = 0;
    let stdin = std::io::stdin();
    let mut input = stdin.lock();
    let mut line = String::new();
 

    // We need to read the input properly
    let mut n = 0;
 

    // Correct approach: read n from stdin
    let mut n_input = String::new();
    std::io::stdin().read_line(&mut n_input).unwrap();
    n = n_input.trim().parse::<usize>().unwrap_or(0);

    if n == 0 {
        println!("0");
        return;
    }

    if n < 0 {
        println!("1");
        return;
    }

    let mut arr = vec![0; n];
    for i in 0..n {
        let mut input_val = String::new();
        std::io::stdin().read_line(&mut input_val).unwrap();
        let val: i32 = input_val.trim().parse().unwrap();
        arr[i] = val;
    }

    let result = trap(&arr);
    println!("{}", result);
}
