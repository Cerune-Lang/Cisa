import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_cpu import CASES, ROUTES, build_case, check_case

ORIGINAL = """const ROM_SIZE: i64 = 17;
program: [u32; ROM_SIZE] = [
    encode_movi(0u8, 10u16),
    encode_movi(0u8, 20u16),
];
"""

class CpuRegressionTests(unittest.TestCase):
    def test_cases_are_distinct(self):
        self.assertEqual(len(CASES), 5)
        self.assertEqual(len(ROUTES), 4)
        self.assertEqual(len({case.name for case in CASES}), 5)
        self.assertEqual([case.expected for case in CASES], [
            "20\n10\n12\n", "call target out of range\n",
            "stack overflow\n", "stack underflow\n",
            "return address out of range\n",
        ])

    def test_only_expected_rom_instruction_changes(self):
        self.assertEqual(build_case(ORIGINAL, CASES[0]), ORIGINAL)
        self.assertIn("encode_call(17u16),", build_case(ORIGINAL, CASES[1]))
        self.assertIn("encode_call(0u16),", build_case(ORIGINAL, CASES[2]))
        self.assertIn("encode_ret(),", build_case(ORIGINAL, CASES[3]))
        bad_ret = build_case(ORIGINAL, CASES[4])
        self.assertIn("encode_movi(0u8, 17u16),", bad_ret)
        self.assertIn("encode_jmp(13u16),", bad_ret)

    def test_fail_closed_if_rom_changes(self):
        with self.assertRaises(ValueError):
            build_case(ORIGINAL.replace("ROM_SIZE: i64 = 17", "ROM_SIZE: i64 = 18"), CASES[1])
        with self.assertRaises(ValueError):
            build_case(ORIGINAL.replace("encode_movi(0u8, 10u16),", "encode_movi(0u8, 8u16),"), CASES[1])

if __name__ == "__main__":
    unittest.main()
