#!/usr/bin/env python3
"""Fault tests of accounting checks using a retained two-block RTL trace."""
import csv
from pathlib import Path
import tempfile
import unittest
from run_single_buffer import matrix, summarize

FIXTURE = Path(__file__).parent/'fixtures/two-block-hybrid.csv'


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.case = next(c for c in matrix() if c['name'] == 'short_default')
        with FIXTURE.open() as stream:
            self.rows = [dict(row) for row in csv.DictReader(stream)]

    def measure(self):
        with tempfile.TemporaryDirectory(prefix='fpga-meter-test-') as directory:
            path = Path(directory)/'blocks.csv'
            with path.open('w') as stream:
                writer = csv.DictWriter(stream,fieldnames=self.rows[0].keys())
                writer.writeheader(); writer.writerows(self.rows)
            return summarize(path,self.case,2,self.case['args'])

    def test_known_window_includes_boundary(self):
        result = self.measure()
        self.assertEqual(result['whole_intervals'],33)
        self.assertEqual(result['whole']['cycles'],34)
        self.assertEqual(result['steady']['start_exclusive'],16)
        self.assertEqual(result['steady']['cycles'],17)
        self.assertEqual(result['steady']['useful'],8)
        self.assertEqual(result['steady']['words_per_cycle'],8/17)

    def test_missing_block_rejected(self):
        self.rows.pop()
        with self.assertRaises(AssertionError): self.measure()

    def test_duplicate_block_rejected(self):
        self.rows[1] = dict(self.rows[0])
        with self.assertRaises(AssertionError): self.measure()

    def test_missing_unavailable_cycle_rejected(self):
        self.rows[-1]['unavailable'] = str(int(self.rows[-1]['unavailable'])-1)
        with self.assertRaises(AssertionError): self.measure()

    def test_stall_misclassified_as_backpressure_rejected(self):
        self.rows[-1]['unavailable'] = str(int(self.rows[-1]['unavailable'])-1)
        self.rows[-1]['intentional'] = '1'  # Total still matches; clock readiness does not.
        with self.assertRaises(AssertionError): self.measure()

    def test_busy_interval_off_by_one_rejected(self):
        self.rows[-1]['a_busy'] = str(int(self.rows[-1]['a_busy'])+1)
        with self.assertRaises(AssertionError): self.measure()

    def test_occupancy_double_count_rejected(self):
        self.rows[-1]['slot_sum'] = str(int(self.rows[-1]['slot_sum'])+1)
        with self.assertRaises(AssertionError): self.measure()

    def test_request_timestamp_corruption_rejected(self):
        self.rows[-1]['request_b'] = str(int(self.rows[-1]['request_b'])+1)
        with self.assertRaises(AssertionError): self.measure()


if __name__ == '__main__':
    unittest.main(verbosity=2)
