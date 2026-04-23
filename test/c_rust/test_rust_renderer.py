from __future__ import annotations

from c_rust.render import CRustRenderer
from core.types import RenderStatus
from test.c_rust.utils import compile_rust


def _render(prefix: str):
    renderer = CRustRenderer()
    return renderer.try_render(prefix)


def test_missing_brace_only_compiles() -> None:
    prefix = """\
fn foo() {
    let x = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_expression_if_missing_else_compiles() -> None:
    prefix = """\
fn foo(a: i32) -> i32 {
    let a = if a > 0 {
        let b = a + 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_nested_blocks_missing_closings_compiles() -> None:
    prefix = """\
fn foo() {
    if true {
        while false {
            let x = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_braces_inside_strings_comments_ignored() -> None:
    prefix = """\
fn foo() {
    let s = "{ }";
    /* { */
    let x = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_complete_snippet_noop_compiles() -> None:
    prefix = """\
fn foo() {
    let x = 1;
}
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_unterminated_string_continues() -> None:
    prefix = """\
fn foo() {
    let s = "unterminated
"""
    result = _render(prefix)
    assert result.status == RenderStatus.CONTINUE


def test_top_level_use_without_semicolon_continues() -> None:
    prefix = "use std::io::{self, Read}"
    result = _render(prefix)

    assert result.status == RenderStatus.CONTINUE
    assert "render_continue:cursor_incomplete" in result.notes


def test_top_level_use_with_semicolon_compiles() -> None:
    prefix = "use std::io::{self, Read};"
    result = _render(prefix)

    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_non_cursor_syntax_error_remains_ok_for_oracle_detection() -> None:
    prefix = """\
fn foo() {
    let x = ;
    let y = 1;
"""
    result = _render(prefix)

    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert not compile.ok

def test_expression_if_missing_else_after_consequence_closed_compiles() -> None:
    # The `if` is in a value context (return), but its consequence block is already
    # closed in the prefix. Renderer should append the `else` as a head insertion
    # so the completed program compiles.
    prefix = """\
fn foo(a: i32) -> i32 {
    return if a > 0 { 1 }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    print(result.artifact.code)
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_let_initializer_closed_without_semicolon_compiles() -> None:
    # The initializer block is already closed, but the semicolon is missing.
    # Renderer should append the semicolon at the cursor so the program compiles.
    prefix = """\
fn foo() {
    let x = { 1 }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr

def test_if_missing_else_but_parent_block_closed_continues() -> None:
    prefix = """\
fn foo(a: i32) {
    if a > 0 { println!("positive"); }
}
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr

def test_let_initializer_closed_but_more_tokens_after_continues() -> None:
    prefix = """\
fn foo() {
    let x = { 1 }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr

def test_if_else_head_before_semicolon_head() -> None:
    prefix = """\
fn foo(a: i32) -> i32 {
  let x = if a > 0 { 1 }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    print(result.artifact.code)
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_if_else_head_before_closing_brace_head() -> None:
    prefix = """\
fn foo() -> i32 {
    let a = 1;
    if a == 0 {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    print(result.artifact.code)
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr

def test_if_else_head_before_closing_brace_head2() -> None:
    prefix = """\
fn foo() -> i32 {
    let a = 1;
    if a == 0 {
        return "str here";
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    print(result.artifact.code)
    compile = compile_rust(result.artifact.code)
    assert not compile.ok # should not compile due to type error


def test_expression_tail_if_from_min_case_compiles() -> None:
    prefix = """\
use std::io;

fn min(a: i32, b: i32, c: i32, d: i32) -> i32 {
    let r = if a < b { a } else { b };
    if c < r {
        c
    }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_expression_tail_else_if_chain_compiles() -> None:
    prefix = """\
fn foo(a: i32, b: i32) -> i32 {
    if a > 0 { 1 } else if b > 0 { 2 }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:fn_tail_if_else_head" in result.notes
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_expression_tail_nested_if_compiles() -> None:
    prefix = """\
fn foo(a: i32, b: i32) -> i32 {
    if a > 0 {
        if b > 0 { 1 } else { 2 }
    }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:fn_tail_if_else_head" in result.notes
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_statement_context_if_does_not_force_else_patch() -> None:
    prefix = """\
fn foo(a: i32) {
    if a > 0 {
        println!("positive");
    }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:if_else" not in result.notes
    assert "render_patch:if_else_head" not in result.notes
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_empty_block_compiles() -> None:
    prefix = """\
fn foo(a: i32) -> i32 {
    match a {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_missing_wildcard_without_comma_compiles() -> None:
    prefix = """\
fn foo(a: i32) -> i32 {
    match a {
        0 => 1
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_missing_wildcard_with_comma_compiles() -> None:
    prefix = """\
fn foo(a: i32) -> i32 {
    match a {
        0 => 1,
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_arm_block_semicolon_compiles() -> None:
    prefix = """\
fn foo(a: i32) {
    match a {
        0 => {
            let x = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_arm_block_closing_brace_compiles() -> None:
    prefix = """\
fn foo(a: i32) -> i32 {
    match a {
        0 => { 1 }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_guard_arm_compiles() -> None:
    prefix = """\
fn foo(a: i32) {
    match a {
        n if n > 0 => {
            let y = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_let_initializer_compiles() -> None:
    prefix = """\
fn foo(a: i32) {
    let x = match a {
        0 => {
            let y = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_type_witness_parse_ok_empty_arm_compiles() -> None:
    prefix = """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Ok(num) => {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_type_witness" in result.notes
    assert result.artifact.code == """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Ok(num) => {

let _: usize = num;
todo!()}
, _ => todo!()}
;}"""
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_type_witness_parse_ok_nonempty_arm_compiles() -> None:
    prefix = """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Ok(num) => {
            if num == 0 {
                println!("zero");
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_type_witness" in result.notes
    assert result.artifact.code == """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Ok(num) => {
            if num == 0 {
                println!("zero");

todo!()
} else { todo!()}
let _: usize = num;
todo!()}
, _ => todo!()}
;}"""
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_type_witness_parse_some_compiles() -> None:
    prefix = """\
fn foo(x: Option<i32>) {
    let val: i32 = match x {
        Some(v) => {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_type_witness" not in result.notes


def test_type_witness_skipped_no_type_annotation() -> None:
    prefix = """\
fn foo(input: &str) {
    let n = match input.trim().parse::<usize>() {
        Ok(num) => {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_type_witness" not in result.notes


def test_type_witness_skipped_err_pattern() -> None:
    prefix = """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Err(e) => {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_type_witness" not in result.notes


def test_type_witness_skipped_turbofish() -> None:
    prefix = """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse::<usize>() {
        Ok(num) => {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_type_witness" not in result.notes


def test_type_witness_skipped_complex_type() -> None:
    prefix = """\
fn foo(input: &str) {
    let n: Vec<usize> = match input.trim().parse() {
        Ok(num) => {
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_type_witness" not in result.notes


def test_match_arm_tail_err_statement_compiles() -> None:
    prefix = """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Ok(num) => { num }
        Err(_) => {
            println!("error");
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_tail" in result.notes
    assert result.artifact.code == """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Ok(num) => { num }
        Err(_) => {
            println!("error");

todo!()}
, _ => todo!()}
;}"""
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_arm_tail_skipped_return() -> None:
    prefix = """\
fn foo(input: &str) {
    let n: usize = match input.trim().parse() {
        Ok(num) => { num }
        Err(_) => {
            return;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_tail" not in result.notes


def test_match_arm_tail_let_tail_compiles() -> None:
    prefix = """\
fn foo(a: i32) -> i32 {
    let x = match a {
        0 => { 1 }
        _ => {
            let y = a + 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:match_arm_tail" in result.notes
    assert result.artifact.code == """\
fn foo(a: i32) -> i32 {
    let x = match a {
        0 => { 1 }
        _ => {
            let y = a + 1;

todo!()}}
;
todo!()}"""
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_implicit_return_arm_block_let_tail_compiles() -> None:
    # Reproduces s842128761: match is the last expression in fn -> i32,
    # so it is the implicit return. The arm block ends with `let result = ...;`
    # which has type (). The renderer must detect implicit-return context and
    # add todo!() to the arm block tail so the arm produces a value.
    prefix = """\
fn foo(a: i32) -> i32 {
    match a {
        0 => {
            let result = a + 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_implicit_return_arm_block_expr_tail_compiles() -> None:
    # Arm block tail is an expression (`a`) that already produces a value.
    # The renderer should NOT insert an extra todo!() here.
    prefix = """\
fn foo(a: i32) -> i32 {
    match a {
        0 => {
            let result = a + 1;
            a
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_multibyte_comments_do_not_break_patch_rules() -> None:
    """Multibyte characters in comments shift byte offsets relative to
    char offsets. Tree-sitter uses byte offsets, so patch rules that
    locate AST nodes by prefix length can miss when multibyte content
    precedes the target node. Reproduced from s804064392 E0317 failure.
    """
    prefix = (
        "// \u6570\u5b66\u306e\u8a08\u7b97 (multibyte comment to shift byte offsets)\n"
        "\n"
        "struct S;\n"
        "\n"
        "impl S {\n"
        "    fn f(x: i32) -> usize {\n"
        "        if x == 0 {\n"
        "            return 0;\n"
    )
    result = _render(prefix)
    assert result.status == RenderStatus.OK, f"unexpected status: {result.notes}"
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_returning_value_closed_if_no_else_tail_compiles() -> None:
    prefix = """\
fn foo(x: i32) -> i32 {
    if x < 0 {
        return 0;
    }
    if x > 0 {
    }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_returning_bool_match_arm_if_tail_compiles() -> None:
    # A legal prefix inside a bool-returning function should render into
    # oracle-consumable code even when a match arm ends with an incomplete
    # value-producing if-expression.
    prefix = """\
fn parse_flag(input: &str) -> bool {
    match input.parse::<i32>() {
        Ok(value) => {
            if value > 0 {
                true
            }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_unsafe_block_if_missing_else_compiles() -> None:
    # fn body tail is `unsafe { if cond { return x; } }`. The `unsafe` block
    # forwards the inner block's tail value, so without a patch the function
    # returns `()` and rustc raises E0317.
    prefix = """\
fn foo(a: i32) -> i32 {
    if a == 0 {
        return 0;
    }
    unsafe {
        if a > 0 {
            return a;
        }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_naked_block_if_missing_else_compiles() -> None:
    # Same bug class with a naked `{ ... }` block as fn tail instead of `unsafe { ... }`.
    prefix = """\
fn foo(a: i32) -> i32 {
    {
        if a > 0 {
            1
        }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_nested_wrappers_if_missing_else_compiles() -> None:
    # Nested `unsafe { unsafe { if ... } }` as fn tail - recursion must go through
    # every wrapper layer, not just the outermost one.
    prefix = """\
fn foo(a: i32) -> i32 {
    unsafe {
        unsafe {
            if a > 0 {
                return a;
            }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_wrapper_with_trailing_stmt_remains_compilable() -> None:
    # Sanity: if the wrapper body has a concrete tail expression *after* a
    # non-tail if, current renderer already handles it - this test guards
    # against a Phase 4 regression.
    prefix = """\
fn foo() -> i32 {
    unsafe {
        if true {
            1;
        }
        42
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_match_arm_wrapper_if_missing_else_compiles() -> None:
    # Match arm value is `unsafe { if cond { ... } }`. FunctionContextRule
    # cannot cover this - the fn tail is `match`, not a TAIL_FORWARDING
    # wrapper - so IfContextRule must recognize the arm-inside-wrapper as a
    # value context and emit the else patch itself.
    prefix = """\
fn foo() -> i32 {
    match 0 {
        _ => unsafe {
            if true {
                1
            }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_else_if_chain_open_consequence_compiles() -> None:
    # Open-consequence counterpart: the sibling branch `{ let a = 1; }` has
    # type `()` which pollutes the chain type; keeping the chain as a tail
    # expression makes it incompatible with the non-() fn return.
    prefix = """\
fn foo(c: usize) -> Result<(), ()> {
    if c == 0 { let a = 1; }
    else if c == 1 { let a = 2;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:fn_tail_if_else" in result.notes
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_complete_if_chain_with_unit_branches_compiles() -> None:
    # Complete if/elif/else chain (no missing else) as fn body tail. Every arm
    # is a statement block of type `()`, so the chain type is `()` and would
    # break compatibility with the non-() fn return. The renderer must
    # downgrade the chain to a statement with an independent fn tail.
    prefix = """\
fn foo(c: usize) -> Result<(), ()> {
    let mut ret: i32 = 0;
    if c == 0 {
        ret = 1;
    } else if c == 1 {
        ret = 2;
    } else {
        ret = 3;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_fully_closed_chain_inside_open_fn_body_compiles() -> None:
    # Counterpart to the previous test: the chain itself is fully closed but
    # the fn body is still open (user may keep adding statements). Chain type
    # is still `()` and must be downgraded; relying on "expression closed"
    # alone would miss this regression.
    prefix = """\
fn foo(c: usize) -> Result<(), ()> {
    let mut ret: i32 = 0;
    if c == 0 {
        ret = 1;
    } else if c == 1 {
        ret = 2;
    } else {
        ret = 3;
    }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_fn_tail_loop_with_break_inside_open_if_compiles() -> None:
    # Cursor lands inside `if` (open consequence). Renderer scaffolds 3 closing
    # braces -> `loop { ... }` becomes the fn tail expression. `break;` makes
    # the loop yield `()`, fn returns Result<(), ()> -> mismatch unless the
    # renderer downgrades the loop to a statement with independent tail.
    prefix = """\
fn foo() -> Result<(), ()> {
    let mut n: i32 = 0;
    loop {
        n += 1;
        if n > 10 {
            break;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_closure_in_let_with_return_tail_compiles() -> None:
    # Closure `|| -> T { ... return X; }` assigned to a let with no trailing `;`.
    # LetContextRule must recognize closure_expression as a value block needing
    # `;` after its close; otherwise the scaffold emits `let f = || {...}` with
    # no semi, and the fn tail patch inserts `todo!()` right after, producing
    # `let f = ... todo!()` which rustc rejects with `expected ;, found todo`.
    prefix = """\
fn foo() -> i32 {
    let mut idx = 0;
    let f = || -> i32 {
        if idx >= 10 {
            return 0;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_closure_in_let_mut_matches_s927_pattern_compiles() -> None:
    # Exact s927 shape: `let mut f = || -> i32 { ... }` (mutable binding plus
    # closure). `let mut` adds a mutable_specifier child to let_declaration but
    # the value field still resolves to closure_expression; regression guard
    # ensuring the new elif branch covers the mut variant too.
    prefix = """\
fn foo() -> i32 {
    let mut idx = 0;
    let mut f = || -> i32 {
        if idx >= 10 {
            return 0;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_closure_in_let_with_match_tail_compiles() -> None:
    # Interplay: MatchContextRule operates on a match inside the closure body
    # (adds `_ => todo!()` wildcard) while LetContextRule closes the outer
    # `let f = || -> i32 { match ... }` with `;`. Both rules must cooperate for
    # the scaffold to compile.
    prefix = """\
fn foo() -> i32 {
    let x: i32 = 0;
    let f = || -> i32 {
        match x {
            1 => return 1,
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_closure_body_tail_let_declaration_compiles() -> None:
    # Closure body tail is a `let` declaration (produces `()`) but the closure
    # declares `-> i32`. No existing rule patches closure body tails: IfRule/
    # MatchRule only trigger on if/match tails, FunctionRule only targets
    # `function_item`. Scaffold closes the closure here with no value tail,
    # rustc rejects with E0308 (mismatched types, expected i32 found ()).
    # Second half of s927: after `if { return 0; }` is complete the model
    # writes a new `let val = ...;` and there is no rule to keep it compiling.
    prefix = """\
fn foo() -> i32 {
    let f = || -> i32 {
        let val = 42;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_closure_body_after_if_return_then_let_matches_s927_compiles() -> None:
    # The exact second-half s927 shape: closure body has a closed
    # `if { return X; }` early-exit followed by a fresh `let val = ...;`.
    # Without ClosureContextRule the closure body tail resolves to the
    # let_declaration and rustc fires `E0308` with the signature hint
    # "consider returning the local binding `val`".
    prefix = """\
fn foo() -> i32 {
    let mut idx: i32 = 0;
    let f = || -> i32 {
        if idx > 0 {
            return 0;
        }
        let val = idx;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_closure_without_return_type_does_not_get_patched() -> None:
    # Closure without explicit `-> T` returns the inferred type (unit here).
    # Body tail = let_declaration = (); no mismatch. ClosureContextRule MUST
    # skip (returns_value=False path) to avoid over-reaching and inserting a
    # spurious `todo!()` that changes a compile-clean prefix into something
    # else. Guards against FP in non-typed-closure patterns the LLM may emit.
    prefix = """\
fn foo() {
    let f = || {
        let x = 42;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert "render_patch:closure_tail" not in result.notes
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_closure_body_tail_if_missing_else_delegates_to_if_rule() -> None:
    # Architectural contract: when closure body tail is `if cond { X }` with a
    # missing `else`, ClosureContextRule MUST skip (IF_MISSING_ELSE) and let
    # IfContextRule handle the value-context patch via find_value_context
    # (closure_expression=VALUE_EXPR, so the walk reaches the outer let).
    # Double-patching would introduce a FP. Renderer may return CONTINUE for
    # this s927 empirical shape (cursor in open consequence + tail expr) due to
    # a separate IfRule bug; CONTINUE is abstention (not FP) and acceptable per
    # FP-first policy. The delegation contract is asserted via note absence
    # regardless of final render status.
    prefix = """\
fn foo() -> i32 {
    let x: i32 = 0;
    let f = || -> i32 {
        if x > 0 {
            1
"""
    result = _render(prefix)
    assert result.status != RenderStatus.FAIL
    assert "render_patch:closure_tail" not in result.notes
    if result.status == RenderStatus.OK:
        assert result.artifact is not None
        compile = compile_rust(result.artifact.code)
        assert compile.ok, compile.stderr


def test_nested_fn_outer_returns_value_inner_unit_compiles() -> None:
    # FunctionRule first-break picks innermost `fn inner` (returns_value=False,
    # early exit) so outer `fn outer -> i32` body tail stays unpatched. s927
    # `fn main -> io::Result<()>` + nested `fn genHash` is the real case.
    prefix = """\
fn outer() -> i32 {
    fn inner() {
        let x = 42;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_nested_fn_both_return_values_compiles() -> None:
    # Inner gets `todo!()` patch but outer body tail = inner function_item
    # (value `()`), outer expected `i32`. Not specific to unit-returning inner.
    prefix = """\
fn outer() -> i32 {
    fn inner() -> u32 {
        let y = 10;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_nested_fn_inner_if_missing_else_open_consequence_outer_needs_tail_compiles() -> None:
    # Inner IF_MISSING_ELSE with `consequence_closed=False` + in_consequence
    # patch (cursor inside an unclosed consequence with statement only).
    # Outer fn body tail is the inner fn item (NEEDS_TODO). Cascade fix is
    # required for outer.
    prefix = """\
fn outer() -> i32 {
    fn inner() -> u32 {
        if 1 > 0 {
            let y = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_nested_fn_inner_if_missing_else_closed_consequence_outer_needs_tail_compiles() -> None:
    # Inner IF_MISSING_ELSE with `consequence_closed=True` (consequence fully
    # written and closed before cursor) exercises the head-expr path
    # (` else { todo!() };` + fn tail todo!()). Outer still has inner fn item
    # as body tail; cascade fix required.
    prefix = """\
fn outer() -> i32 {
    fn inner() -> u32 {
        if 1 > 0 {
            42
        }
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = compile_rust(result.artifact.code)
    assert compile.ok, compile.stderr


def test_nested_closure_outer_returns_value_inner_unit_does_not_produce_fp() -> None:
    # ClosureRule has a symmetric first-break gap mirroring FunctionRule's.
    # In practice this shape trips tree-sitter: nested `|| ... || ...`
    # unclosed collapses the whole source_file into one ERROR node, so
    # `_cursor_needs_continuation` returns CONTINUE before any rule runs.
    # The ClosureRule FP is therefore unreachable today, cushioned by
    # parse fragility rather than a deliberate abstention. This test locks
    # in the no-FP contract: if tree-sitter recovery ever improves and the
    # tree becomes clean, CONTINUE drops to OK, the scaffold renders an
    # unpatched outer closure tail, compile fails, and this test fires.
    prefix = """\
fn foo() {
    let f = || -> i32 {
        let g = || {
            let x = 10;
"""
    result = _render(prefix)
    assert result.status != RenderStatus.FAIL
    if result.status == RenderStatus.OK:
        assert result.artifact is not None
        compile = compile_rust(result.artifact.code)
        assert compile.ok, compile.stderr
