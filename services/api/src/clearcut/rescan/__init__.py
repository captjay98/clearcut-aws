"""Selective-rescan orchestration: safe item and evidence carry-forward.

The rescan module owns the cross-module carry-forward workflow but never reads
another module's storage. It depends only on typed module ports (revision plan,
item lineage, evidence lineage) and the shared frozen DTOs in
``clearcut.rescan.application.models``. Owning modules (scripts, detection,
research) implement the ports against their own tables.
"""
