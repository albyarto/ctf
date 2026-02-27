# HiddenX.jar – Reverse Engineering Walkthrough

## 1) Inspect the JAR

```bash
jar tf HiddenX.jar
```

You should see:
- `ctf/hiddenx/Main.class`
- `payload.bin`

This tells us the challenge logic is in `Main.class` and encrypted data is in `payload.bin`.

## 2) Decompile the class logic

Use `javap` (or CFR/JADX):

```bash
javap -classpath HiddenX.jar -c -p ctf.hiddenx.Main
```

Main observations from bytecode:
- Input length must be **36**.
- A custom checker `O0O0O(String)` validates the whole 36-byte input using two 32-bit rolling states.
- If valid, program takes `input.substring(3, 23)` (20 chars) as a key seed.
- It computes CRC32 of `Main.class` and derives a 32-byte key stream from this 20-char substring.
- It loads `payload.bin`, transforms it, and writes `output.zip` when first bytes are `PK`.

## 3) Reconstruct helper functions in Python

Implement equivalent Python functions for:
- `check(s)` for `O0O0O(String)` (36-byte validation)
- `crc_main_class()` for `O0O0O()`
- `derive_key(crc, s20, 32)` for `O0O0O(int, String, int)`
- `decrypt(payload, key)` for `O0O0O(byte[], byte[])`

This lets you iterate quickly without rerunning Java manually.

## 4) Solve the 36-byte checker with an SMT solver

The input checker is essentially a 64-bit final-state constraint over 36 symbolic bytes.
Use z3/angr/cvc5 style solving:
- 36 symbolic 8-bit bytes (`c0..c35`)
- initial states:
  - `a = -863691923`
  - `b = -1144959338`
- per byte update exactly as decompiled
- final constraints:
  - `a == -1052301703`
  - `b == 247639510`

Any model that satisfies this gives a valid 36-char unlock string.

> Note: Constrain to printable ASCII first for readable results; if unsat, relax to full byte range.

## 5) Extract the 20-char decryption segment

From solved 36-byte string `inp`:

```python
key20 = inp[3:23]
```

This exact slice is used by the binary.

## 6) Decrypt `payload.bin` and recover ZIP

- compute CRC32 of `ctf/hiddenx/Main.class` bytes from inside JAR
- derive 32-byte key using `key20`
- run decrypt transform over `payload.bin`
- save as `output.zip`

If correct, `output.zip` should be a valid ZIP (not just `PK` header).

## 7) Unzip and read the flag

```bash
unzip -l output.zip
unzip output.zip -d out
cat out/*
```

The extracted text/file should contain the final flag.

## 8) Practical fallback (if you only need extraction)

You can patch the JAR check (or reimplement main flow externally) to skip boolean validation,
but you still need the **correct 20-char segment** to decrypt meaningful content.
So solving the checker is still the intended robust path.

