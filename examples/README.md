# Query your own records with the RTL

`sensor_records.csv` is a synthetic, reproducible example: each row has an ID, a key in 0..99, and fourteen unsigned 32-bit samples. The accelerator selects rows whose key is below a threshold and returns their exact unsigned 64-bit payload sum. Rejected rows return `selected=0,sum=0`.

```sh
python3 examples/query_records.py examples/sensor_records.csv --threshold 25
```

Read `build/query-demo/query_results.csv` for results produced by the native RTL executable. The testbench independently checks the same source fixture; Python handles file conversion and orchestration. Use `--arch b_only`, `hybrid`, `header_first` or `cached_b` to select an implementation, and a new `--output-dir` for each run. Requires the Verilator toolchain described in `docs/setup.md`.

Your CSV must use the exact example header and contain 1..128 rows with distinct unsigned IDs, keys 0..99, and decimal uint32 samples. Short inputs are padded to the prototype's fixed 128-record geometry; only input-row results are exported, while timing includes all padding. This is an executable simulation prototype, not a board driver or a general database API.
