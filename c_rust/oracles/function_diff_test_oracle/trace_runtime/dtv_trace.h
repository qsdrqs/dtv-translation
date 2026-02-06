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

#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <time.h>
#include <string.h>

#define DTV_JSON_ARGS_CAP 4096
#define DTV_JSON_PTR_ARGS_CAP 2048
#define DTV_JSON_RET_CAP 512

typedef struct {
    char *buf;
    size_t cap;
    size_t len;
    int first;
} DtvJsonArray;

static inline void dtv_json_array_init(DtvJsonArray *arr, char *buf, size_t cap) {
    arr->buf = buf;
    arr->cap = cap;
    arr->len = 0;
    arr->first = 1;
    arr->len += snprintf(arr->buf + arr->len, arr->cap - arr->len, "[");
}

static inline void dtv_json_array_sep(DtvJsonArray *arr) {
    if (!arr->first) {
        arr->len += snprintf(arr->buf + arr->len, arr->cap - arr->len, ",");
    }
    arr->first = 0;
}

static inline const char *dtv_json_array_finish(DtvJsonArray *arr) {
    arr->len += snprintf(arr->buf + arr->len, arr->cap - arr->len, "]");
    return arr->buf;
}

static inline void dtv_json_array_push_unsupported(DtvJsonArray *arr, const char *reason) {
    dtv_json_array_sep(arr);
    arr->len += snprintf(
        arr->buf + arr->len,
        arr->cap - arr->len,
        "{\"ty\":\"unsupported\",\"skip\":true,\"reason\":\"%s\"}",
        reason
    );
}

static inline const char *dtv_json_value_unsupported(char *buf, size_t cap, const char *reason) {
    snprintf(buf, cap, "{\"ty\":\"unsupported\",\"skip\":true,\"reason\":\"%s\"}", reason);
    return buf;
}

#define DTV_JSON_ARRAY_DECLARE(name, cap) \
    char name##_buf[cap]; \
    DtvJsonArray name; \
    dtv_json_array_init(&name, name##_buf, sizeof(name##_buf))

#define DTV_JSON_DEFINE_SIGNED(tag, ctype, fmt, cast) \
    static inline void dtv_json_array_push_##tag(DtvJsonArray *arr, ctype value) { \
        dtv_json_array_sep(arr); \
        arr->len += snprintf( \
            arr->buf + arr->len, \
            arr->cap - arr->len, \
            "{\"ty\":\"" #tag "\",\"val\":" fmt "}", \
            cast value \
        ); \
    } \
    static inline void dtv_json_array_push_ptr_##tag(DtvJsonArray *arr, const ctype *value) { \
        dtv_json_array_sep(arr); \
        if (value == NULL) { \
            arr->len += snprintf( \
                arr->buf + arr->len, \
                arr->cap - arr->len, \
                "{\"ty\":\"ptr_" #tag "\",\"val\":null}" \
            ); \
        } else { \
            arr->len += snprintf( \
                arr->buf + arr->len, \
                arr->cap - arr->len, \
                "{\"ty\":\"ptr_" #tag "\",\"val\":" fmt "}", \
                cast (*value) \
            ); \
        } \
    } \
    static inline const char *dtv_json_value_##tag(char *buf, size_t cap, ctype value) { \
        snprintf(buf, cap, "{\"ty\":\"" #tag "\",\"val\":" fmt "}", cast value); \
        return buf; \
    } \
    static inline const char *dtv_json_value_ptr_##tag(char *buf, size_t cap, const ctype *value) { \
        if (value == NULL) { \
            snprintf(buf, cap, "{\"ty\":\"ptr_" #tag "\",\"val\":null}"); \
        } else { \
            snprintf(buf, cap, "{\"ty\":\"ptr_" #tag "\",\"val\":" fmt "}", cast (*value)); \
        } \
        return buf; \
    }

#define DTV_JSON_DEFINE_UNSIGNED(tag, ctype, fmt, cast) \
    static inline void dtv_json_array_push_##tag(DtvJsonArray *arr, ctype value) { \
        dtv_json_array_sep(arr); \
        arr->len += snprintf( \
            arr->buf + arr->len, \
            arr->cap - arr->len, \
            "{\"ty\":\"" #tag "\",\"val\":" fmt "}", \
            cast value \
        ); \
    } \
    static inline void dtv_json_array_push_ptr_##tag(DtvJsonArray *arr, const ctype *value) { \
        dtv_json_array_sep(arr); \
        if (value == NULL) { \
            arr->len += snprintf( \
                arr->buf + arr->len, \
                arr->cap - arr->len, \
                "{\"ty\":\"ptr_" #tag "\",\"val\":null}" \
            ); \
        } else { \
            arr->len += snprintf( \
                arr->buf + arr->len, \
                arr->cap - arr->len, \
                "{\"ty\":\"ptr_" #tag "\",\"val\":" fmt "}", \
                cast (*value) \
            ); \
        } \
    } \
    static inline const char *dtv_json_value_##tag(char *buf, size_t cap, ctype value) { \
        snprintf(buf, cap, "{\"ty\":\"" #tag "\",\"val\":" fmt "}", cast value); \
        return buf; \
    } \
    static inline const char *dtv_json_value_ptr_##tag(char *buf, size_t cap, const ctype *value) { \
        if (value == NULL) { \
            snprintf(buf, cap, "{\"ty\":\"ptr_" #tag "\",\"val\":null}"); \
        } else { \
            snprintf(buf, cap, "{\"ty\":\"ptr_" #tag "\",\"val\":" fmt "}", cast (*value)); \
        } \
        return buf; \
    }

static inline void dtv_json_array_push_bool(DtvJsonArray *arr, bool value) {
    dtv_json_array_sep(arr);
    arr->len += snprintf(
        arr->buf + arr->len,
        arr->cap - arr->len,
        "{\"ty\":\"bool\",\"val\":%d}",
        value ? 1 : 0
    );
}

static inline void dtv_json_array_push_ptr_bool(DtvJsonArray *arr, const bool *value) {
    dtv_json_array_sep(arr);
    if (value == NULL) {
        arr->len += snprintf(
            arr->buf + arr->len,
            arr->cap - arr->len,
            "{\"ty\":\"ptr_bool\",\"val\":null}"
        );
    } else {
        arr->len += snprintf(
            arr->buf + arr->len,
            arr->cap - arr->len,
            "{\"ty\":\"ptr_bool\",\"val\":%d}",
            (*value) ? 1 : 0
        );
    }
}

static inline const char *dtv_json_value_bool(char *buf, size_t cap, bool value) {
    snprintf(buf, cap, "{\"ty\":\"bool\",\"val\":%d}", value ? 1 : 0);
    return buf;
}

static inline const char *dtv_json_value_ptr_bool(char *buf, size_t cap, const bool *value) {
    if (value == NULL) {
        snprintf(buf, cap, "{\"ty\":\"ptr_bool\",\"val\":null}");
    } else {
        snprintf(buf, cap, "{\"ty\":\"ptr_bool\",\"val\":%d}", (*value) ? 1 : 0);
    }
    return buf;
}

static inline void dtv_json_array_push_f32(DtvJsonArray *arr, float value) {
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    dtv_json_array_sep(arr);
    arr->len += snprintf(
        arr->buf + arr->len,
        arr->cap - arr->len,
        "{\"ty\":\"f32\",\"val\":\"0x%08x\"}",
        bits
    );
}

static inline void dtv_json_array_push_ptr_f32(DtvJsonArray *arr, const float *value) {
    dtv_json_array_sep(arr);
    if (value == NULL) {
        arr->len += snprintf(
            arr->buf + arr->len,
            arr->cap - arr->len,
            "{\"ty\":\"ptr_f32\",\"val\":null}"
        );
    } else {
        uint32_t bits = 0;
        memcpy(&bits, value, sizeof(bits));
        arr->len += snprintf(
            arr->buf + arr->len,
            arr->cap - arr->len,
            "{\"ty\":\"ptr_f32\",\"val\":\"0x%08x\"}",
            bits
        );
    }
}

static inline const char *dtv_json_value_f32(char *buf, size_t cap, float value) {
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    snprintf(buf, cap, "{\"ty\":\"f32\",\"val\":\"0x%08x\"}", bits);
    return buf;
}

static inline const char *dtv_json_value_ptr_f32(char *buf, size_t cap, const float *value) {
    if (value == NULL) {
        snprintf(buf, cap, "{\"ty\":\"ptr_f32\",\"val\":null}");
    } else {
        uint32_t bits = 0;
        memcpy(&bits, value, sizeof(bits));
        snprintf(buf, cap, "{\"ty\":\"ptr_f32\",\"val\":\"0x%08x\"}", bits);
    }
    return buf;
}

static inline void dtv_json_array_push_f64(DtvJsonArray *arr, double value) {
    uint64_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    dtv_json_array_sep(arr);
    arr->len += snprintf(
        arr->buf + arr->len,
        arr->cap - arr->len,
        "{\"ty\":\"f64\",\"val\":\"0x%016llx\"}",
        (unsigned long long)bits
    );
}

static inline void dtv_json_array_push_ptr_f64(DtvJsonArray *arr, const double *value) {
    dtv_json_array_sep(arr);
    if (value == NULL) {
        arr->len += snprintf(
            arr->buf + arr->len,
            arr->cap - arr->len,
            "{\"ty\":\"ptr_f64\",\"val\":null}"
        );
    } else {
        uint64_t bits = 0;
        memcpy(&bits, value, sizeof(bits));
        arr->len += snprintf(
            arr->buf + arr->len,
            arr->cap - arr->len,
            "{\"ty\":\"ptr_f64\",\"val\":\"0x%016llx\"}",
            (unsigned long long)bits
        );
    }
}

static inline const char *dtv_json_value_f64(char *buf, size_t cap, double value) {
    uint64_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    snprintf(buf, cap, "{\"ty\":\"f64\",\"val\":\"0x%016llx\"}", (unsigned long long)bits);
    return buf;
}

static inline const char *dtv_json_value_ptr_f64(char *buf, size_t cap, const double *value) {
    if (value == NULL) {
        snprintf(buf, cap, "{\"ty\":\"ptr_f64\",\"val\":null}");
    } else {
        uint64_t bits = 0;
        memcpy(&bits, value, sizeof(bits));
        snprintf(buf, cap, "{\"ty\":\"ptr_f64\",\"val\":\"0x%016llx\"}", (unsigned long long)bits);
    }
    return buf;
}

DTV_JSON_DEFINE_SIGNED(i8, int8_t, "%lld", (long long))
DTV_JSON_DEFINE_SIGNED(i16, int16_t, "%lld", (long long))
DTV_JSON_DEFINE_SIGNED(i32, int32_t, "%lld", (long long))
DTV_JSON_DEFINE_SIGNED(i64, int64_t, "%lld", (long long))
DTV_JSON_DEFINE_SIGNED(isize, ptrdiff_t, "%lld", (long long))

DTV_JSON_DEFINE_UNSIGNED(u8, uint8_t, "%llu", (unsigned long long))
DTV_JSON_DEFINE_UNSIGNED(u16, uint16_t, "%llu", (unsigned long long))
DTV_JSON_DEFINE_UNSIGNED(u32, uint32_t, "%llu", (unsigned long long))
DTV_JSON_DEFINE_UNSIGNED(u64, uint64_t, "%llu", (unsigned long long))
DTV_JSON_DEFINE_UNSIGNED(usize, size_t, "%llu", (unsigned long long))

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

/* Emit trace event with optional JSON payloads */
static inline void dtv_emit_trace_extra(
    const char *kind,
    const char *id,
    const char *args_json,
    const char *ret_json,
    const char *ptr_args_json
) {
    if (!dtv_trace_enabled) return;

    int64_t timestamp = dtv_get_timestamp_us();
    fprintf(stderr, "{\"kind\":\"%s\",\"id\":\"%s\"", kind, id);
    if (args_json) {
        fprintf(stderr, ",\"args\":%s", args_json);
    }
    if (ret_json) {
        fprintf(stderr, ",\"ret\":%s", ret_json);
    }
    if (ptr_args_json) {
        fprintf(stderr, ",\"ptr_args\":%s", ptr_args_json);
    }
    fprintf(stderr, ",\"timestamp\":%lld,\"depth\":%d}\n", (long long)timestamp, dtv_trace_depth);
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

static inline void dtv_trace_function_enter_args(const char *func_name, const char *args_json) {
    dtv_emit_trace_extra("func_enter", func_name, args_json, NULL, NULL);
    dtv_trace_depth++;
}

static inline void dtv_trace_function_exit_ret(
    const char *func_name,
    const char *ret_json,
    const char *ptr_args_json
) {
    dtv_trace_depth--;
    dtv_emit_trace_extra("func_exit", func_name, NULL, ret_json, ptr_args_json);
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
