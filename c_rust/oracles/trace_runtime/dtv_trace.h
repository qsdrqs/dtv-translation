/**
 * DTV Trace Runtime Library (C header)
 *
 * Provides trace instrumentation for differential testing.
 *
 * Usage:
 *   #include "dtv_trace.h"
 *
 *   int my_function(int x) {
 *       dtv_trace_function_enter("my_function");
 *
 *       if (x > 0) {
 *           dtv_trace_block_enter("block_1");
 *           // ... code ...
 *           dtv_trace_block_exit("block_1");
 *       }
 *
 *       dtv_trace_function_exit("my_function");
 *       return x * 2;
 *   }
 *
 * Trace output is written to stderr in JSON format, one event per line:
 *   {"kind":"func_enter","id":"my_function","timestamp":1234567890,"depth":0}
 *   {"kind":"block_enter","id":"block_1","timestamp":1234567891,"depth":1}
 *   {"kind":"block_exit","id":"block_1","timestamp":1234567892,"depth":1}
 *   {"kind":"func_exit","id":"my_function","timestamp":1234567893","depth":0}
 */

#ifndef DTV_TRACE_H
#define DTV_TRACE_H

#include <stdio.h>
#include <stdint.h>
#include <time.h>

/* Global trace state */
static int dtv_trace_depth = 0;
static int dtv_trace_enabled = 1;

/* Get current timestamp in microseconds */
static inline int64_t dtv_get_timestamp_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

/* Emit trace event as JSON to stderr */
static inline void dtv_emit_trace(const char *kind, const char *id) {
    if (!dtv_trace_enabled) return;

    int64_t timestamp = dtv_get_timestamp_us();
    fprintf(stderr, "{\"kind\":\"%s\",\"id\":\"%s\",\"timestamp\":%lld,\"depth\":%d}\n",
            kind, id, (long long)timestamp, dtv_trace_depth);
    fflush(stderr);
}

/* Function-level tracing */
static inline void dtv_trace_function_enter(const char *func_name) {
    dtv_emit_trace("func_enter", func_name);
    dtv_trace_depth++;
}

static inline void dtv_trace_function_exit(const char *func_name) {
    dtv_trace_depth--;
    dtv_emit_trace("func_exit", func_name);
}

/* Block-level tracing */
static inline void dtv_trace_block_enter(const char *block_id) {
    dtv_emit_trace("block_enter", block_id);
    dtv_trace_depth++;
}

static inline void dtv_trace_block_exit(const char *block_id) {
    dtv_trace_depth--;
    dtv_emit_trace("block_exit", block_id);
}

/* Control trace enablement (for testing/debugging) */
static inline void dtv_trace_enable(void) {
    dtv_trace_enabled = 1;
}

static inline void dtv_trace_disable(void) {
    dtv_trace_enabled = 0;
}

#endif /* DTV_TRACE_H */
