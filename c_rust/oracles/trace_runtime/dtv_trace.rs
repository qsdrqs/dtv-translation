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
    if !TRACE_ENABLED.load(Ordering::Relaxed) {
        return;
    }

    let timestamp = get_timestamp_us();
    let depth = TRACE_DEPTH.load(Ordering::Relaxed);

    eprintln!(
        r#"{{"kind":"{}","id":"{}","timestamp":{},"depth":{}}}"#,
        kind, id, timestamp, depth
    );
}

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
