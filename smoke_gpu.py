#!/usr/bin/env python3
"""Smoke test: HF model download (cache dir) + GPU loading."""

import os
import sys
import time

def main() -> None:
    # 1. Check HF_HOME
    hf_home = os.environ.get("HF_HOME", "(not set)")
    print(f"HF_HOME = {hf_home}")
    if hf_home == "(not set)":
        print("WARNING: HF_HOME not set, will use default ~/.cache/huggingface")

    # Check cache dir exists / writable
    if hf_home != "(not set)":
        os.makedirs(hf_home, exist_ok=True)
        test_file = os.path.join(hf_home, ".smoke_test")
        try:
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            print(f"  Cache dir writable: YES")
        except OSError as e:
            print(f"  Cache dir writable: NO ({e})")
            sys.exit(1)

    # 2. Check torch + CUDA
    print("\n--- torch + CUDA ---")
    import torch
    print(f"torch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
            mem = torch.cuda.get_device_properties(i).total_memory
            print(f"    Memory: {mem / 1e9:.1f} GB")
        print(f"bf16 supported: {torch.cuda.is_bf16_supported()}")
    else:
        print("ERROR: No CUDA device found!")
        sys.exit(1)

    # 3. Download tokenizer (lightweight, tests HF hub connectivity + cache)
    print("\n--- HF tokenizer download ---")
    model_name = "Qwen/Qwen3-4B-Instruct-2507"
    import transformers
    print(f"transformers version: {transformers.__version__}")

    t0 = time.time()
    tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
    dt = time.time() - t0
    print(f"Tokenizer loaded in {dt:.1f}s")
    print(f"  Vocab size: {tokenizer.vocab_size}")

    # Verify cache location
    if hf_home != "(not set)":
        hub_dir = os.path.join(hf_home, "hub")
        if os.path.isdir(hub_dir):
            entries = os.listdir(hub_dir)
            print(f"  HF hub cache entries: {entries[:5]}")
        else:
            print(f"  WARNING: {hub_dir} does not exist after download")

    # 4. Load model to GPU
    print("\n--- Model loading to GPU ---")
    t0 = time.time()
    model = transformers.AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )
    model.eval()
    dt = time.time() - t0
    print(f"Model loaded in {dt:.1f}s")
    print(f"  Model device: {next(model.parameters()).device}")
    print(f"  Model dtype: {next(model.parameters()).dtype}")

    # Check GPU memory usage
    for i in range(torch.cuda.device_count()):
        alloc = torch.cuda.memory_allocated(i) / 1e9
        reserved = torch.cuda.memory_reserved(i) / 1e9
        print(f"  GPU {i}: allocated={alloc:.2f}GB, reserved={reserved:.2f}GB")

    # 5. Token generation speed benchmark
    print("\n--- Generation speed benchmark ---")
    prompt = "Translate the following C code into Rust, keep the same function order:\n```c\n#include <stdio.h>\nint main() {\n    int n;\n    scanf(\"%d\", &n);\n    for (int i = 0; i < n; i++) {\n        printf(\"%d\\n\", i * i);\n    }\n    return 0;\n}\n```"
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    input_len = inputs.input_ids.shape[1]
    print(f"Prompt tokens: {input_len}")

    for max_tokens in [64, 256, 512]:
        # warmup on first run
        if max_tokens == 64:
            with torch.no_grad():
                model.generate(inputs.input_ids, max_new_tokens=4)

        t0 = time.time()
        with torch.no_grad():
            outputs = model.generate(inputs.input_ids, max_new_tokens=max_tokens)
        dt = time.time() - t0
        gen_tokens = outputs.shape[1] - input_len
        tps = gen_tokens / dt if dt > 0 else 0
        print(f"  max_new={max_tokens:>4}: {gen_tokens:>4} tokens in {dt:.2f}s = {tps:.1f} tok/s")

    # Quick sanity check
    result = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True)
    print(f"  Last output preview: {result[:120]!r}...")

    # 6. SDPA / Flash Attention diagnostics
    print("\n--- Attention backend diagnostics ---")
    print(f"  CUDA capability: {torch.cuda.get_device_capability(0)}")
    print(f"  flash_sdp_enabled: {torch.backends.cuda.flash_sdp_enabled()}")
    print(f"  mem_efficient_sdp_enabled: {torch.backends.cuda.mem_efficient_sdp_enabled()}")
    print(f"  math_sdp_enabled: {torch.backends.cuda.math_sdp_enabled()}")
    if hasattr(torch.backends.cuda, 'cudnn_sdp_enabled'):
        print(f"  cudnn_sdp_enabled: {torch.backends.cuda.cudnn_sdp_enabled()}")

    # Check what attn_implementation the model is actually using
    attn_impl = getattr(model.config, '_attn_implementation', 'unknown')
    print(f"  model attn_implementation: {attn_impl}")

    # Check if flash_attn / flash_attn_3 packages are installed
    try:
        import flash_attn
        print(f"  flash_attn (FA2): {flash_attn.__version__}")
    except ImportError:
        print("  flash_attn (FA2): NOT INSTALLED")
    try:
        import flash_attn_3
        print(f"  flash_attn_3 (FA3): {flash_attn_3.__version__}")
    except (ImportError, AttributeError):
        try:
            import flash_attn_3  # noqa: F811
            print("  flash_attn_3 (FA3): INSTALLED (no __version__)")
        except ImportError:
            print("  flash_attn_3 (FA3): NOT INSTALLED")

    # Check cuDNN version
    print(f"  cuDNN version: {torch.backends.cudnn.version()}")
    print(f"  cuDNN enabled: {torch.backends.cudnn.enabled}")

    # 7. Benchmark with different attn_implementation
    for attn_impl_name in ["sdpa", "flash_attention_3"]:
        print(f"\n--- Benchmark: attn_implementation={attn_impl_name} ---")
        try:
            model_bench = transformers.AutoModelForCausalLM.from_pretrained(
                model_name,
                device_map="auto",
                torch_dtype=torch.bfloat16,
                attn_implementation=attn_impl_name,
            )
            model_bench.eval()
            # warmup
            with torch.no_grad():
                model_bench.generate(inputs.input_ids, max_new_tokens=4)
            t0 = time.time()
            with torch.no_grad():
                outputs_bench = model_bench.generate(inputs.input_ids, max_new_tokens=256)
            dt = time.time() - t0
            gen_tokens = outputs_bench.shape[1] - input_len
            tps = gen_tokens / dt if dt > 0 else 0
            print(f"  256 tokens: {gen_tokens} in {dt:.2f}s = {tps:.1f} tok/s")
            del model_bench
            torch.cuda.empty_cache()
        except Exception as e:
            print(f"  FAILED: {e}")

    print("\n=== ALL SMOKE TESTS PASSED ===")


if __name__ == "__main__":
    main()
