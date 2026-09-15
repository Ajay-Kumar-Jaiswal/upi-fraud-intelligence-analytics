# src/validation/

Validation logic in this project lives INLINE in the cleaning modules
(src/cleaning/*.py - e.g. amount parse failures, invalid PAN/Aadhaar
formats, and identity collisions are computed and flagged as part of
cleaning, not as a separate pass) and in the pytest suite (tests/), which
serves as the executable validation contract for the pipeline.

This directory was reserved in the original architecture for a
standalone rule-engine module, but was not needed in practice — Stage 4
(validation) was fully satisfied by the inline flags + 121 passing tests
instead. Left in place (with this note) rather than silently deleted, so
the project structure still matches what was proposed in Stage 1/2.
