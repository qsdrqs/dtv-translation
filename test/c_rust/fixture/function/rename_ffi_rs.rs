fn add_offset(x: i32, offset: i32) -> i32 {
    clamp_value(x + offset, -100, 100)
}
