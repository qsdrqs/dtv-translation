from __future__ import annotations

from js_ts.render import JSToTSRenderer
from core.types import RenderStatus
from test.js_ts.utils import check_typescript


def _render(prefix: str):
    renderer = JSToTSRenderer()
    return renderer.try_render(prefix)


def test_missing_brace_only_compiles() -> None:
    prefix = """\
function foo() {
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_nested_blocks_missing_closings_compiles() -> None:
    prefix = """\
function foo() {
    if (true) {
        while (false) {
            const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_braces_inside_strings_comments_ignored() -> None:
    prefix = """\
function foo() {
    const s: string = "{ }";
    /* { */
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_complete_snippet_noop_compiles() -> None:
    prefix = """\
function foo() {
    const x: number = 1;
}
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_unterminated_string_continues() -> None:
    prefix = """\
function foo() {
    const s: string = "unterminated
"""
    result = _render(prefix)
    assert result.status == RenderStatus.CONTINUE


def test_empty_prefix_continues() -> None:
    result = _render("")
    assert result.status == RenderStatus.CONTINUE


def test_function_with_return_type_compiles() -> None:
    prefix = """\
function add(a: number, b: number): number {
    return a + b;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_function_missing_return_compiles() -> None:
    prefix = """\
function foo(): number {
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_function_missing_return_with_unicode_compiles() -> None:
    prefix = """\
function foo(): number {
    const s: string = "\u4f60\u597d";
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_try_without_catch_with_unicode_compiles() -> None:
    prefix = """\
function foo() {
    const s: string = "\u4f60\u597d";
    try {
        const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_try_closed_in_prefix_gets_catch() -> None:
    prefix = "function foo() { try { const x = 1; }"
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_try_without_catch_compiles() -> None:
    prefix = """\
function foo() {
    try {
        const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_if_else_compiles() -> None:
    prefix = """\
function foo(x: number): number {
    if (x > 0) {
        return x;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_arrow_function_compiles() -> None:
    prefix = """\
const add = (a: number, b: number): number => {
    return a + b;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_class_method_compiles() -> None:
    prefix = """\
class Calculator {
    add(a: number, b: number): number {
        return a + b;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_switch_case_compiles() -> None:
    prefix = """\
function foo(x: number): string {
    switch (x) {
        case 1:
            return "one";
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_for_loop_compiles() -> None:
    prefix = """\
function sum(n: number): number {
    let total: number = 0;
    for (let i = 0; i < n; i++) {
        total += i;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_non_cursor_type_error_remains_ok() -> None:
    prefix = """\
function foo() {
    const x: number = "hello";
    const y: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert not compile.ok


def test_template_literal_braces_ignored() -> None:
    prefix = """\
function foo() {
    const s: string = `hello ${"world"}`;
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_single_quote_string_compiles() -> None:
    prefix = """\
function foo() {
    const s: string = '{ }';
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_group_stack_inside_block() -> None:
    prefix = """\
function foo() {
    if (true) {
        const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert result.artifact.group_stack is not None
    from core.types import Granularity
    kinds = tuple(f.kind for f in result.artifact.group_stack)
    assert kinds == (Granularity.FUNC, Granularity.BLOCK)


def test_prefix_without_exports_compiles_no_global_conflicts() -> None:
    prefix = """\
var toString = Object.prototype.toString;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_prefix_with_exports_unchanged() -> None:
    prefix = """\
var toString = Object.prototype.toString;
export {};
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_function_expression_missing_return_compiles() -> None:
    prefix = """\
const fn = function (): number {
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout


def test_group_stack_function_name() -> None:
    prefix = """\
function bar() {
    const x: number = 1;
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    assert result.artifact.group_stack is not None
    assert any(f.name_id == "bar" for f in result.artifact.group_stack)


def test_continue_on_syntax_incomplete() -> None:
    """Render should return CONTINUE when the prefix is syntactically
    incomplete at the cursor (e.g. import without source clause)."""
    result = _render("import { x }\n")
    assert result.status == RenderStatus.CONTINUE


def test_ok_on_complete_import() -> None:
    """Render should return OK when a complete import statement is present."""
    prefix = """\
import { readFileSync } from "fs";
"""
    result = _render(prefix)
    assert result.status == RenderStatus.OK
    assert result.artifact is not None
    compile = check_typescript(result.artifact.code)
    assert compile.ok, compile.stdout
