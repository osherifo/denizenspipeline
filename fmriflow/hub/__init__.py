"""Artifact Hub — a decoupled, multi-tier registry for sharing fMRIflow
artifacts (error-KB entries, modules, configs, pipeline configs, heudiconv
heuristics, feature arrays) across local / within-lab / cross-lab tiers.

Design: the hub is an **install/browse layer, not a runtime resolution
tier**. Installing copies an artifact into the normal user tier, where the
existing resolvers already find it — so nothing in the pipeline hot path
changes. Sources are git repositories described by a ``hub.json`` manifest;
a ``HubBackend`` Protocol keeps other transports (dir/http/s3) pluggable.

Remove the whole feature by deleting this package plus the gated call-sites
in ``server/app.py``, ``server/routes/hub.py``, and ``core/paths.py``.
"""

from __future__ import annotations

from fmriflow.hub.service import HubService

__all__ = ["HubService"]
