#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility entry point for the CDR demo.

The implementation lives in the :mod:`cdr` package so the simulation,
recovery loop, plotting, and CLI orchestration stay testable and reusable.
"""

from cdr.cli import main


if __name__ == "__main__":
    main()
