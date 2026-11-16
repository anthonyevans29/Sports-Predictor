**2026-11-16 — The graph rebuild's receipt line carries the run's peak (addendum 407 item 3; #1010; #1031).**
- **Ruling (407 item 3, verbatim in part):** "THE PEAK LINE (#1010 ...): BUILD IT. One small PR, lane B: the "peak" object beside memory_limit on the rebuild's receipt line, on success and on failure alike ... (a) It touches the receipt's JSON line only ... (b) A file that cannot be read is null with its reason in the line, never a failed run."
- **Why:** the host's first run (404 item 1(c): 247.7 s, 1,346,489 assertions) had no measured peak. systemd reported no MemoryPeak for the unit, which exits and loses its cgroup when the build is done.
- **What landed:**
  - `peak` on every line: the parent's and the staging child's peak RSS, and the unit cgroup's own peak read while it runs;
  - each part null with its reason where it cannot be read.
- **Receipt:** the real 1× build in the 1536M rig wrote 429.5 MiB process and 1,345 MiB cgroup (RSS plus cache), each equal to the rig's own measure.
- **Next:** it rides the next tag. The first host figure is the first 10:20Z run after that deploy, read by the architect's block. #1010 stays open.
