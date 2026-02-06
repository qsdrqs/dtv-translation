/**
 * DTV Trace Runtime Library (Rust module)
 *
 * Provides trace instrumentation for differential testing.
 *
 * Usage:
 *   mod dtv_trace;
 *   use dtv_trace::{trace_function_enter, trace_function_exit, trace_block};
 *
 *   fn my_function(x: i32) -> i32 {
 *       trace_function_enter("my_function");
 *
 *       if x > 0 {
 *           trace_block!("block_1", {
 *               // ... code ...
 *           });
 *       }
 *
 *       trace_function_exit("my_function");
 *       x * 2
 *   }
 *
 * Trace output is written to stderr in JSON format, one event per line.
 */

use std::sync::atomic::{AtomicI32, AtomicBool, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/* Global trace state */
static TRACE_DEPTH: AtomicI32 = AtomicI32::new(0);
static TRACE_ENABLED: AtomicBool = AtomicBool::new(true);

/* Get current timestamp in microseconds */
#[inline]
fn get_timestamp_us() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_micros() as i64
}

/* Emit trace event as JSON to stderr */
#[inline]
fn emit_trace(kind: &str, id: &str) {
    emit_trace_extra(kind, id, None, None, None);
}

#[inline]
fn emit_trace_extra(
    kind: &str,
    id: &str,
    args_json: Option<&str>,
    ret_json: Option<&str>,
    ptr_args_json: Option<&str>,
) {
    if !TRACE_ENABLED.load(Ordering::Relaxed) {
        return;
    }

    let timestamp = get_timestamp_us();
    let depth = TRACE_DEPTH.load(Ordering::Relaxed);

    let mut line = String::new();
    line.push_str("{\"kind\":\"");
    line.push_str(kind);
    line.push_str("\",\"id\":\"");
    line.push_str(id);
    line.push('"');
    if let Some(args) = args_json {
        line.push_str(",\"args\":");
        line.push_str(args);
    }
    if let Some(ret) = ret_json {
        line.push_str(",\"ret\":");
        line.push_str(ret);
    }
    if let Some(ptr_args) = ptr_args_json {
        line.push_str(",\"ptr_args\":");
        line.push_str(ptr_args);
    }
    line.push_str(&format!(",\"timestamp\":{},\"depth\":{}}}", timestamp, depth));
    eprintln!("{}", line);
}

pub struct DtvJsonArray {
    buf: String,
    first: bool,
}

impl DtvJsonArray {
    pub fn new() -> Self {
        DtvJsonArray {
            buf: String::from("["),
            first: true,
        }
    }

    pub fn push_json(&mut self, value: String) {
        if !self.first {
            self.buf.push(',');
        }
        self.first = false;
        self.buf.push_str(&value);
    }

    pub fn finish(mut self) -> String {
        self.buf.push(']');
        self.buf
    }
}

pub fn json_value_unsupported(reason: &str) -> String {
    format!(
        "{{\"ty\":\"unsupported\",\"skip\":true,\"reason\":\"{}\"}}",
        reason
    )
}

fn json_value_null(ptr_tag: &str) -> String {
    format!("{{\"ty\":\"{}\",\"val\":null}}", ptr_tag)
}

fn json_value_empty_slice(ptr_tag: &str) -> String {
    format!(
        "{{\"ty\":\"{}\",\"skip\":true,\"reason\":\"empty_slice\"}}",
        ptr_tag
    )
}

macro_rules! json_int {
    (
        $value_fn:ident,
        $ref_fn:ident,
        $raw_ptr_fn:ident,
        $slice_fn:ident,
        $array_fn:ident,
        $ty:ty,
        $tag:expr,
        $ptr_tag:expr
    ) => {
        pub fn $value_fn(value: $ty) -> String {
            format!("{{\"ty\":\"{}\",\"val\":{}}}", $tag, value)
        }

        pub fn $ref_fn(value: &$ty) -> String {
            format!("{{\"ty\":\"{}\",\"val\":{}}}", $ptr_tag, *value)
        }

        pub fn $raw_ptr_fn(value: *const $ty) -> String {
            if value.is_null() {
                json_value_null($ptr_tag)
            } else {
                unsafe { format!("{{\"ty\":\"{}\",\"val\":{}}}", $ptr_tag, *value) }
            }
        }

        pub fn $slice_fn(value: &[$ty]) -> String {
            if let Some(first) = value.first() {
                format!("{{\"ty\":\"{}\",\"val\":{}}}", $ptr_tag, *first)
            } else {
                json_value_empty_slice($ptr_tag)
            }
        }

        pub fn $array_fn<const N: usize>(value: &[$ty; N]) -> String {
            if let Some(first) = value.get(0) {
                format!("{{\"ty\":\"{}\",\"val\":{}}}", $ptr_tag, *first)
            } else {
                json_value_empty_slice($ptr_tag)
            }
        }
    };
}

macro_rules! json_float {
    (
        $value_fn:ident,
        $ref_fn:ident,
        $raw_ptr_fn:ident,
        $slice_fn:ident,
        $array_fn:ident,
        $ty:ty,
        $tag:expr,
        $ptr_tag:expr,
        $fmt:expr
    ) => {
        pub fn $value_fn(value: $ty) -> String {
            format!(
                "{{\"ty\":\"{}\",\"val\":\"0x{}\"}}",
                $tag,
                format!($fmt, value.to_bits())
            )
        }

        pub fn $ref_fn(value: &$ty) -> String {
            format!(
                "{{\"ty\":\"{}\",\"val\":\"0x{}\"}}",
                $ptr_tag,
                format!($fmt, value.to_bits())
            )
        }

        pub fn $raw_ptr_fn(value: *const $ty) -> String {
            if value.is_null() {
                json_value_null($ptr_tag)
            } else {
                unsafe {
                    format!(
                        "{{\"ty\":\"{}\",\"val\":\"0x{}\"}}",
                        $ptr_tag,
                        format!($fmt, (*value).to_bits())
                    )
                }
            }
        }

        pub fn $slice_fn(value: &[$ty]) -> String {
            if let Some(first) = value.first() {
                format!(
                    "{{\"ty\":\"{}\",\"val\":\"0x{}\"}}",
                    $ptr_tag,
                    format!($fmt, first.to_bits())
                )
            } else {
                json_value_empty_slice($ptr_tag)
            }
        }

        pub fn $array_fn<const N: usize>(value: &[$ty; N]) -> String {
            if let Some(first) = value.get(0) {
                format!(
                    "{{\"ty\":\"{}\",\"val\":\"0x{}\"}}",
                    $ptr_tag,
                    format!($fmt, first.to_bits())
                )
            } else {
                json_value_empty_slice($ptr_tag)
            }
        }
    };
}

pub fn json_value_bool(value: bool) -> String {
    format!("{{\"ty\":\"bool\",\"val\":{}}}", if value { 1 } else { 0 })
}

pub fn json_value_ref_bool(value: &bool) -> String {
    format!(
        "{{\"ty\":\"ptr_bool\",\"val\":{}}}",
        if *value { 1 } else { 0 }
    )
}

pub fn json_value_raw_ptr_bool(value: *const bool) -> String {
    if value.is_null() {
        json_value_null("ptr_bool")
    } else {
        unsafe {
            format!(
                "{{\"ty\":\"ptr_bool\",\"val\":{}}}",
                if *value { 1 } else { 0 }
            )
        }
    }
}

pub fn json_value_slice_bool(value: &[bool]) -> String {
    if let Some(first) = value.first() {
        format!(
            "{{\"ty\":\"ptr_bool\",\"val\":{}}}",
            if *first { 1 } else { 0 }
        )
    } else {
        json_value_empty_slice("ptr_bool")
    }
}

pub fn json_value_array_bool<const N: usize>(value: &[bool; N]) -> String {
    if let Some(first) = value.get(0) {
        format!(
            "{{\"ty\":\"ptr_bool\",\"val\":{}}}",
            if *first { 1 } else { 0 }
        )
    } else {
        json_value_empty_slice("ptr_bool")
    }
}

pub fn json_value_char(value: char) -> String {
    format!("{{\"ty\":\"char\",\"val\":{}}}", value as u32)
}

pub fn json_value_ref_char(value: &char) -> String {
    format!(
        "{{\"ty\":\"ptr_char\",\"val\":{}}}",
        (*value) as u32
    )
}

pub fn json_value_raw_ptr_char(value: *const char) -> String {
    if value.is_null() {
        json_value_null("ptr_char")
    } else {
        unsafe { format!("{{\"ty\":\"ptr_char\",\"val\":{}}}", (*value) as u32) }
    }
}

pub fn json_value_slice_char(value: &[char]) -> String {
    if let Some(first) = value.first() {
        format!("{{\"ty\":\"ptr_char\",\"val\":{}}}", (*first) as u32)
    } else {
        json_value_empty_slice("ptr_char")
    }
}

pub fn json_value_array_char<const N: usize>(value: &[char; N]) -> String {
    if let Some(first) = value.get(0) {
        format!("{{\"ty\":\"ptr_char\",\"val\":{}}}", (*first) as u32)
    } else {
        json_value_empty_slice("ptr_char")
    }
}

json_int!(
    json_value_i8,
    json_value_ref_i8,
    json_value_raw_ptr_i8,
    json_value_slice_i8,
    json_value_array_i8,
    i8,
    "i8",
    "ptr_i8"
);
json_int!(
    json_value_i16,
    json_value_ref_i16,
    json_value_raw_ptr_i16,
    json_value_slice_i16,
    json_value_array_i16,
    i16,
    "i16",
    "ptr_i16"
);
json_int!(
    json_value_i32,
    json_value_ref_i32,
    json_value_raw_ptr_i32,
    json_value_slice_i32,
    json_value_array_i32,
    i32,
    "i32",
    "ptr_i32"
);
json_int!(
    json_value_i64,
    json_value_ref_i64,
    json_value_raw_ptr_i64,
    json_value_slice_i64,
    json_value_array_i64,
    i64,
    "i64",
    "ptr_i64"
);
json_int!(
    json_value_isize,
    json_value_ref_isize,
    json_value_raw_ptr_isize,
    json_value_slice_isize,
    json_value_array_isize,
    isize,
    "isize",
    "ptr_isize"
);
json_int!(
    json_value_u8,
    json_value_ref_u8,
    json_value_raw_ptr_u8,
    json_value_slice_u8,
    json_value_array_u8,
    u8,
    "u8",
    "ptr_u8"
);
json_int!(
    json_value_u16,
    json_value_ref_u16,
    json_value_raw_ptr_u16,
    json_value_slice_u16,
    json_value_array_u16,
    u16,
    "u16",
    "ptr_u16"
);
json_int!(
    json_value_u32,
    json_value_ref_u32,
    json_value_raw_ptr_u32,
    json_value_slice_u32,
    json_value_array_u32,
    u32,
    "u32",
    "ptr_u32"
);
json_int!(
    json_value_u64,
    json_value_ref_u64,
    json_value_raw_ptr_u64,
    json_value_slice_u64,
    json_value_array_u64,
    u64,
    "u64",
    "ptr_u64"
);
json_int!(
    json_value_usize,
    json_value_ref_usize,
    json_value_raw_ptr_usize,
    json_value_slice_usize,
    json_value_array_usize,
    usize,
    "usize",
    "ptr_usize"
);

json_float!(
    json_value_f32,
    json_value_ref_f32,
    json_value_raw_ptr_f32,
    json_value_slice_f32,
    json_value_array_f32,
    f32,
    "f32",
    "ptr_f32",
    "{:08x}"
);
json_float!(
    json_value_f64,
    json_value_ref_f64,
    json_value_raw_ptr_f64,
    json_value_slice_f64,
    json_value_array_f64,
    f64,
    "f64",
    "ptr_f64",
    "{:016x}"
);

/* Function-level tracing */
#[inline]
pub fn trace_function_enter(func_name: &str) {
    emit_trace("func_enter", func_name);
    TRACE_DEPTH.fetch_add(1, Ordering::Relaxed);
}

#[inline]
pub fn trace_function_exit(func_name: &str) {
    TRACE_DEPTH.fetch_sub(1, Ordering::Relaxed);
    emit_trace("func_exit", func_name);
}

#[inline]
pub fn trace_function_enter_args(func_name: &str, args_json: &str) {
    emit_trace_extra("func_enter", func_name, Some(args_json), None, None);
    TRACE_DEPTH.fetch_add(1, Ordering::Relaxed);
}

#[inline]
pub fn trace_function_exit_ret(func_name: &str, ret_json: Option<&str>, ptr_args_json: Option<&str>) {
    TRACE_DEPTH.fetch_sub(1, Ordering::Relaxed);
    emit_trace_extra("func_exit", func_name, None, ret_json, ptr_args_json);
}

/* Block-level tracing */
#[inline]
pub fn trace_block_enter(block_id: &str) {
    emit_trace("block_enter", block_id);
    TRACE_DEPTH.fetch_add(1, Ordering::Relaxed);
}

#[inline]
pub fn trace_block_exit(block_id: &str) {
    TRACE_DEPTH.fetch_sub(1, Ordering::Relaxed);
    emit_trace("block_exit", block_id);
}

/* Macro for convenient block tracing with RAII */
#[macro_export]
macro_rules! trace_block {
    ($block_id:expr, $body:expr) => {{
        trace_block_enter($block_id);
        let _guard = BlockExitGuard::new($block_id);
        $body
    }};
}

/* RAII guard for automatic block exit tracing */
pub struct BlockExitGuard {
    block_id: String,
}

impl BlockExitGuard {
    #[inline]
    pub fn new(block_id: &str) -> Self {
        BlockExitGuard {
            block_id: block_id.to_string(),
        }
    }
}

impl Drop for BlockExitGuard {
    #[inline]
    fn drop(&mut self) {
        trace_block_exit(&self.block_id);
    }
}

/* Control trace enablement (for testing/debugging) */
#[allow(dead_code)]
pub fn trace_enable() {
    TRACE_ENABLED.store(true, Ordering::Relaxed);
}

#[allow(dead_code)]
pub fn trace_disable() {
    TRACE_ENABLED.store(false, Ordering::Relaxed);
}
