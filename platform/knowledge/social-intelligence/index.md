---
okf_version: "0.2"
title: Social Intelligence knowledge bundle
description: Portable business concepts, metrics, policies, and computations.
---

# Social Intelligence knowledge bundle

This OKF 0.2 starter bundle is the machine-discoverable knowledge layer for the
platform. It complements—not replaces—the versioned schemas in
[`platform/contracts`](../../contracts/README.md).

- [Platforms](platforms/index.md)
- [Datasets](datasets/index.md)
- [Metrics](metrics/index.md)
- [Computations](computations/index.md)
- [Policies](policies/index.md)
- [Playbooks](playbooks/index.md)

`catalog.json` is a deterministic discovery index generated from concept
frontmatter. Run `python platform/scripts/build_okf_bundle.py --bundle
platform/knowledge/social-intelligence` after changing concepts.
