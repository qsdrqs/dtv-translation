from __future__ import annotations

from dataclasses import dataclass

from c_rust.render.context_rules.base import ContextRule, ContextRegistry, ancestor_of_type, PatchPlan, Analysis


@dataclass(frozen=True)
class MatchArmTypeWitnessContext:
    arm_block_start: int | None = None
    typed_let_type: str | None = None
    binding_ident: str | None = None


_SAFE_WITNESS_TYPES: frozenset[str] = frozenset({
    "u8", "u16", "u32", "u64", "u128", "usize",
    "i8", "i16", "i32", "i64", "i128", "isize",
    "f32", "f64",
    "bool",
    "String",
})


def _enclosing_typed_let(match_node):
    let_node = ancestor_of_type(match_node, ["let_declaration"])
    if let_node is None:
        return None, None
    value_node = let_node.child_by_field_name("value")
    if value_node is None:
        return None, None
    if value_node.id != match_node.id:
        return None, None
    type_node = let_node.child_by_field_name("type")
    if type_node is None:
        return None, None
    return let_node, type_node


def _extract_safe_type(type_node, prefix_bytes: bytes) -> str | None:
    type_text = prefix_bytes[type_node.start_byte:type_node.end_byte].decode("utf-8").strip()
    if type_text in _SAFE_WITNESS_TYPES:
        return type_text
    return None


def _scrutinee_is_untyped_parse(match_node, prefix_bytes: bytes) -> bool:
    value_node = match_node.child_by_field_name("value")
    if value_node is None or value_node.type != "call_expression":
        return False
    func_node = value_node.child_by_field_name("function")
    if func_node is None:
        return False
    if func_node.type != "field_expression":
        return False
    for child in func_node.children:
        if child.type == "field_identifier":
            name = prefix_bytes[child.start_byte:child.end_byte].decode("utf-8")
            if name == "parse":
                return True
    return False


def _extract_ok_or_some_ident(pattern_node, prefix_bytes: bytes) -> tuple[str | None, str | None]:
    if pattern_node is None:
        return None, None
    inner = pattern_node
    if inner.type == "match_pattern":
        named = inner.named_children
        if len(named) != 1:
            return None, None
        inner = named[0]
    if inner.type != "tuple_struct_pattern":
        return None, None
    type_child = inner.child_by_field_name("type")
    if type_child is None:
        return None, None
    variant = prefix_bytes[type_child.start_byte:type_child.end_byte].decode("utf-8")
    if variant not in ("Ok", "Some"):
        return None, None
    ident_children = [
        c for c in inner.named_children
        if c.id != type_child.id and c.type == "identifier"
    ]
    if len(ident_children) != 1:
        return None, None
    ident = prefix_bytes[ident_children[0].start_byte:ident_children[0].end_byte].decode("utf-8")
    return variant, ident


class MatchArmTypeWitnessRule(ContextRule):
    key = "match_arm_type_witness"
    node_types = ("match_expression",)

    def apply_analysis(self, nodes, *, anchor, end_byte: int, prefix_bytes: bytes, registry: ContextRegistry) -> None:
        for match_node in nodes:
            _, type_node = _enclosing_typed_let(match_node)
            if type_node is None:
                continue
            safe_type = _extract_safe_type(type_node, prefix_bytes)
            if safe_type is None:
                continue
            if not _scrutinee_is_untyped_parse(match_node, prefix_bytes):
                continue

            match_block = match_node.child_by_field_name("body")
            if match_block is None:
                continue
            for child in match_block.named_children:
                if child.type != "match_arm":
                    continue
                arm_value = child.child_by_field_name("value")
                if arm_value is None or arm_value.type != "block":
                    continue
                if not (arm_value.start_byte <= end_byte < arm_value.end_byte):
                    continue
                tail = arm_value.named_children[-1] if arm_value.named_children else None
                if tail is not None and tail.type not in (
                    "expression_statement",
                    "let_declaration",
                    "empty_statement",
                    "macro_invocation",
                ):
                        continue

                pattern_node = child.child_by_field_name("pattern")
                variant, ident = _extract_ok_or_some_ident(pattern_node, prefix_bytes)
                if variant is None or ident is None:
                    continue

                registry.add(
                    self.key,
                    MatchArmTypeWitnessContext(
                        arm_block_start=arm_value.start_byte,
                        typed_let_type=safe_type,
                        binding_ident=ident,
                    ),
                )

    def apply_patch(self, plan: PatchPlan, analysis: Analysis) -> None:
        for ctx in self.get_contexts(analysis):
            if not isinstance(ctx, MatchArmTypeWitnessContext):
                continue
            if ctx.arm_block_start is None or ctx.typed_let_type is None or ctx.binding_ident is None:
                continue
            text = f"let _: {ctx.typed_let_type} = {ctx.binding_ident};\ntodo!()"
            plan.insert_before(ctx.arm_block_start, text)
            plan.notes.append("render_patch:match_arm_type_witness")
            break
