# DTV Trace Runtime

This directory contains trace runtime libraries for C and Rust, used by differential testing oracles.

## Files

- `dtv_trace.h`: C header-only trace library
- `dtv_trace.rs`: Rust trace module

## JSON Trace Format

Each trace event is emitted to stderr as a single-line JSON object:

```json
{"kind":"func_enter","id":"my_function","timestamp":1234567890,"depth":0}
{"kind":"block_enter","id":"block_1","timestamp":1234567891,"depth":1}
{"kind":"block_exit","id":"block_1","timestamp":1234567892,"depth":1}
{"kind":"func_exit","id":"my_function","timestamp":1234567893,"depth":0}
```

### Fields

- `kind`: Event type (`func_enter`, `func_exit`, `block_enter`, `block_exit`)
- `id`: Function name or block ID
- `timestamp`: Microsecond timestamp (monotonic clock for C, UNIX epoch for Rust)
- `depth`: Current call/block nesting depth

## C Usage

```c
#include "dtv_trace.h"

int factorial(int n) {
    dtv_trace_function_enter("factorial");

    if (n <= 1) {
        dtv_trace_block_enter("base_case");
        dtv_trace_block_exit("base_case");
        dtv_trace_function_exit("factorial");
        return 1;
    }

    dtv_trace_block_enter("recursive_case");
    int result = n * factorial(n - 1);
    dtv_trace_block_exit("recursive_case");

    dtv_trace_function_exit("factorial");
    return result;
}
```

## Rust Usage

```rust
mod dtv_trace;
use dtv_trace::{trace_function_enter, trace_function_exit, trace_block_enter, trace_block_exit};

fn factorial(n: i32) -> i32 {
    trace_function_enter("factorial");

    let result = if n <= 1 {
        trace_block_enter("base_case");
        let r = 1;
        trace_block_exit("base_case");
        r
    } else {
        trace_block_enter("recursive_case");
        let r = n * factorial(n - 1);
        trace_block_exit("recursive_case");
        r
    };

    trace_function_exit("factorial");
    result
}
```

### Using the `trace_block!` Macro (Rust)

For convenience, Rust code can use the `trace_block!` macro with RAII for automatic exit:

```rust
#[macro_use]
mod dtv_trace;
use dtv_trace::{trace_function_enter, trace_function_exit};

fn factorial(n: i32) -> i32 {
    trace_function_enter("factorial");

    let result = if n <= 1 {
        trace_block!("base_case", 1)
    } else {
        trace_block!("recursive_case", n * factorial(n - 1))
    };

    trace_function_exit("factorial");
    result
}
```

## Instrumentation

### C Instrumentation (Automatic)

The `c_rust/oracles/instrumenter.py` module automatically instruments C code by:
1. Parsing C AST with pycparser
2. Inserting `dtv_trace_function_enter/exit` at function boundaries
3. Inserting `dtv_trace_block_enter/exit` at semantic block boundaries
4. Assigning unique block IDs

### Rust Instrumentation (LLM-Driven)

For Rust, block IDs are extracted from instrumented C code and injected into the LLM prompt:
- "In C block_1 corresponds to the if branch at line X"
- "Generate Rust code with trace_block!(\"block_1\") at the equivalent location"

This leverages the LLM's understanding of C-to-Rust correspondence without requiring Rust AST analysis.

## Design Notes

1. **Trace to stderr**: Keeps stdout clean for actual program output comparison
2. **JSON format**: Easy to parse and filter
3. **Depth tracking**: Helps visualize call/block nesting and detect mismatches
4. **Timestamp optional**: Used for debugging but not required for correctness comparison
5. **Header-only C**: No linking required; just `#include "dtv_trace.h"`
6. **Rust module**: Copied into generated Rust code as a module
