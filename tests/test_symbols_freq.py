"""Tests for the --freq flag in the symbols command."""

import pytest

pytestmark = pytest.mark.integration


class TestSymbolsFreq:
    def test_freq_flag_sorts_by_frequency(self, cli):
        """Test that --freq sorts symbols by frequency (most common first)."""
        # Get symbols with --freq flag
        result = cli.run("symbols", "src/helper.ts", "--freq", "--limit", "20")
        assert result.returncode == 0

        lines = result.stdout.strip().splitlines()
        assert len(lines) > 0

        # Extract symbol names from output (format: "line-range kind name")
        symbol_names = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                # Format: "line-range kind name"
                name = parts[2]
                symbol_names.append(name)

        # Count occurrences of each name
        from collections import Counter

        counts = Counter(symbol_names)

        # Verify that symbols are sorted by frequency (descending)
        # The first symbol should have count >= last symbol's count
        if len(symbol_names) >= 2:
            first_count = counts[symbol_names[0]]
            last_count = counts[symbol_names[-1]]
            msg = f"First symbol '{symbol_names[0]}' (count={first_count})"
            msg += f" should be >= last '{symbol_names[-1]}' (count={last_count})"
            assert first_count >= last_count, msg

    def test_freq_flag_with_ties_sorts_alphabetically(self, cli):
        """Test that symbols with same frequency are sorted alphabetically."""
        result = cli.run("symbols", "src/helper.ts", "--freq", "--limit", "20")
        assert result.returncode == 0

        lines = result.stdout.strip().splitlines()

        # Extract symbol names and their frequencies
        from collections import Counter

        symbol_names = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                symbol_names.append(parts[2])

        counts = Counter(symbol_names)

        # Find groups with the same frequency
        freq_groups = {}
        for name, count in counts.items():
            freq_groups.setdefault(count, []).append(name)

        # For each frequency group with multiple items, verify alphabetical order
        for count, names in freq_groups.items():
            if len(names) > 1:
                # These names should appear in alphabetical order in the output
                # Find their positions in the output
                positions = []
                for name in names:
                    for i, line in enumerate(lines):
                        parts = line.split()
                        if len(parts) >= 3 and parts[2] == name:
                            positions.append((i, name))
                            break

                # Sort by position and verify names are alphabetical
                positions.sort()
                ordered_names = [name for _, name in positions]
                assert ordered_names == sorted(ordered_names), (
                    f"Symbols with frequency {count} should be alphabetically sorted: {ordered_names}"
                )

    def test_without_freq_flag_maintains_original_order(self, cli):
        """Test that without --freq, symbols maintain their original order (by line number)."""
        result = cli.run("symbols", "src/helper.ts", "--limit", "10")
        assert result.returncode == 0

        lines = result.stdout.strip().splitlines()

        # Extract line numbers from output (format: "start-end kind name")
        line_numbers = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                # Parse the line range (e.g., "5-10" or "5")
                line_range = parts[0]
                if "-" in line_range:
                    start_line = int(line_range.split("-")[0])
                else:
                    start_line = int(line_range)
                line_numbers.append(start_line)

        # Verify that line numbers are in ascending order
        assert line_numbers == sorted(line_numbers), (
            f"Without --freq, symbols should be ordered by line number: {line_numbers}"
        )
