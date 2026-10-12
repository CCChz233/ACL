# Third-party sources

The original benchmark data, reference patches, tests, container images, model weights and paper PDFs are not redistributed by this repository. Downloaded upstream repositories remain independent local checkouts or source archives. Preserve each upstream license and citation when using its materials.

| Source | Official project | Local purpose |
|---|---|---|
| SWE-bench Pro | https://github.com/scaleapi/SWE-bench_Pro-os | Code evaluation |
| Terminal-Bench | https://github.com/harbor-framework/terminal-bench | Terminal evaluation |
| Terminal-Bench 2.1 | https://github.com/harbor-framework/terminal-bench-2-1 | Reference terminal evaluation |
| SWE-bench | https://github.com/SWE-bench/SWE-bench | Verified evaluation |
| Verified Mini | https://huggingface.co/datasets/MariusHobbhahn/swe-bench-verified-mini | Development checks |
| SEAL | https://github.com/Continual-Intelligence/SEAL | Mechanism reference |
| Absolute Zero Reasoner | https://github.com/LeapLabTHU/Absolute-Zero-Reasoner | Self-play reference |
| SWE-smith | https://github.com/SWE-bench/SWE-smith | Candidate code training data |
| SWE-Gym | https://github.com/SWE-Gym/SWE-Gym | Candidate code training data |
| Tmax | https://github.com/hamishivi/tmax | Candidate terminal training data |

Pinned benchmark revisions and file hashes are in `benchmarks/sources.lock.json`. Preparation status is separate from runtime validation. No training results or novelty claims are established yet.
