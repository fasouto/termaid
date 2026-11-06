"""Allow running termaid as a module: python -m termaid"""
import sys

from .cli import main

sys.exit(main())
