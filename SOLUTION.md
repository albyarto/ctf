# HiddenX.jar auto-solver (beginner friendly)

Use the script `solve_hiddenx.py` in this repo.

## 1) Run it

```bash
python3 solve_hiddenx.py --jar HiddenX.jar --output output.zip
```

What it does automatically:
1. Reads `ctf/hiddenx/Main.class` and `payload.bin` from `HiddenX.jar`
2. Solves the 36-byte checker with z3
3. Builds the 32-byte decryption key from `substring(3,23)`
4. Decrypts `payload.bin`
5. Writes `output.zip`
6. Opens `output.zip` and prints flag text

## 2) If `z3` is missing

Install z3, then run again:

```bash
sudo apt-get update && sudo apt-get install -y z3
python3 solve_hiddenx.py --jar HiddenX.jar --output output.zip
```

## 3) Optional: inspect ZIP manually

```bash
unzip -l output.zip
unzip output.zip -d out
cat out/*
```

