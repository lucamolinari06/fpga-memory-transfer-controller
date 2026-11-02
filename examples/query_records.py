#!/usr/bin/env python3
"""Run the SystemVerilog filter/sum accelerator on a user CSV (no Python DUT)."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['id', 'key'] + ['sample_' + str(i) for i in range(14)]


def load_records(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError('CSV header must be: ' + ','.join(FIELDS))
        records = []
        for number, row in enumerate(reader, 2):
            if None in row or any(row[k] is None for k in FIELDS):
                raise ValueError('Wrong column count on CSV line ' + str(number))
            try:
                values = [int(row[k], 10) for k in FIELDS]
            except ValueError as exc:
                raise ValueError('Expected unsigned decimal integers on line ' + str(number)) from exc
            if any(value < 0 or value > 0xffffffff for value in values):
                raise ValueError('Values must fit uint32 on line ' + str(number))
            if values[1] > 99:
                raise ValueError('Key must be 0..99 on line ' + str(number))
            records.append(values)
    if not 1 <= len(records) <= 128:
        raise ValueError('This fixed-geometry prototype supports 1..128 records per CSV.')
    if len({row[0] for row in records}) != len(records):
        raise ValueError('Record IDs must be unique.')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, help='id,key,sample_0,...,sample_13; 1..128 rows')
    parser.add_argument('--threshold', type=int, default=50, help='select key < threshold (0..100)')
    parser.add_argument('--arch', choices=['b_only', 'hybrid', 'header_first', 'cached_b'], default='header_first')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/query-demo')
    args = parser.parse_args()
    if not 0 <= args.threshold <= 100:
        parser.error('--threshold must be 0..100')
    try:
        original = load_records(args.csv)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'query.json').exists() or (out / 'runs').exists():
        parser.error('Output directory already contains a query; choose a new --output-dir.')
    records = [row[:] for row in original]
    used = {row[0] for row in records}
    padding_id = 0xffffffff
    while len(records) < 128:
        while padding_id in used:
            padding_id -= 1
        records.append([padding_id, 99] + [0] * 14)
        used.add(padding_id)
    fixture = out / 'input.hex'
    fixture.write_text(''.join(f'{word:08x}\n' for row in records for word in row))
    command = ['bash', 'scripts/test_application.sh', '--query', '--dataset-hex', str(fixture),
               '--arch', args.arch, '--threshold', str(args.threshold), '--workload', 'sequential',
               '--queries', '1', '--output-dir', str(out)]
    code = subprocess.run(command, cwd=ROOT).returncode
    if code:
        return code
    paths = list((out / 'runs').glob('*/records.csv'))
    if len(paths) != 1:
        raise RuntimeError('Expected exactly one native result stream, found ' + str(len(paths)))
    with paths[0].open(newline='') as stream:
        native = list(csv.DictReader(stream))
    if len(native) != 128:
        raise RuntimeError('Native run did not return all 128 padded records.')
    destination = out / 'query_results.csv'
    with destination.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'key', 'selected', 'sum'])
        writer.writeheader()
        for record, result in zip(original, native):
            if int(result['id']) != record[0]:
                raise RuntimeError('Unexpected native result order.')
            # Result fields come from the RTL CSV, never host recomputation.
            writer.writerow(dict(id=result['id'], key=record[1], selected=result['selected'], sum=result['sum']))
    (out / 'input-metadata.json').write_text(json.dumps({
        'input_records': len(original), 'native_records': 128,
        'padding_records': 128-len(original), 'threshold': args.threshold, 'arch': args.arch,
        'meaning': 'query_results.csv copies native RTL results for input rows; performance includes all 128 padded records.',
    }, indent=2) + '\n')
    print('Native RTL results:', destination)
    if len(original) < 128:
        print('Timing includes', 128-len(original), 'padding records; this is a fixed 128-record prototype.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
