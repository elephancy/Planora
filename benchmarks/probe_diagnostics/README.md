# Retained diagnostic sources

These files preserve historical benchmark investigations. Normal product code and CI do not invoke these diagnostic entry points.

The unused `_execute_module` helpers in PU-PROJ v12–v19 and v21–v24 now raise an explicit error instead of executing supplied bytes. This source repair does not update their historical supervisors, freeze manifests, certificates or source hashes. Those original hash-pinned replay paths must reject the changed runner bytes; this branch is intentionally incompatible with those old replay freezes.

The original source remains available in Git history. Do not automatically repin a supervisor, regenerate a certificate, or launch a replay to accommodate this change. Any future replay requires a separate review of its full source and execution boundary. Other reviewed sealed-byte loaders and their existing exact admission checks remain unchanged.
