# Pillars native missing-core fixture

Exact SCI/WHT/CON crop of the local public JWST F090W association mosaic. The JSON
manifest records original and fixture SHA-256, source size, full native dimensions,
crop bounds, and core coordinates. Astropy sliced the celestial WCS; no science,
weight or context samples were altered. CON remains CON rather than a fabricated
CTX product. The current loader detects the six missing core samples from SCI/WHT.

The 2 x 3 native hole is at crop rows 32:34, columns 32:35 (zero-based half-open).
It has zero WHT and zero values in all five CON layers. Expected boundary-median
presentation estimate is float32 489.00608825683594. The algorithm and specimen
provenance remain distinct from a recovered stellar flux claim.

Specification: [BRIDGE-MEDIAN-001](../../../docs/reprojection_bridge_algorithm.md).
