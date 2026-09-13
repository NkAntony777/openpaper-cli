#!/usr/bin/env python3
"""Shared fixtures for the openpaper-cli test suite."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

POC = Path(__file__).parent / "fixtures" / "poc_output"


@pytest.fixture
def poc_root(tmp_path):
    """Copy the PoC fixture (bibliography + outline + checkpoint) into a tmp dir."""
    dest = tmp_path / "paper"
    shutil.copytree(POC, dest)
    return dest
