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
