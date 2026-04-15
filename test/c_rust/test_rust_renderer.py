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
