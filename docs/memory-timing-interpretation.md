# Interpretation and review checkpoint — 2026-10-21

The completed timing extension supports a conditional architectural result: **hybrid helps when parallel service and early delivery offset the slowest segment, but it does not generally beat the better single-memory baseline.** All numbers below are actual RTL simulation results with exploratory cycle settings, not physical hardware predictions.

## Which conclusions survive, change, or remain conditional?

| Historical conclusion | Verdict after the new experiments | Evidence and mechanism |
| --- | --- | --- |
| S=1 wins against both under the original default parameters | **Survives in all three legacy overlays; does not generalize to recommended settings.** | Legacy hybrid steady rates P1/P2/P3 are 0.410359/0.376436/0.352177 and beat both baselines. Under the recommended full-rate A setting, every tested P1 sequential split loses to A. A's available service, not its SRAM label, determines this result. |
| S=3 delivers early but ties B completion | **Completion tie changes to a win in the legacy overlays; early first-word benefit survives.** | Legacy P1 mean first-word cycles A/B/H = 6.042/12.459/6.028, mean completion = 27.042/19.459/17.766. B-only and hybrid each record 1,022 hits and two completed closed-row setups in the measured window. Hybrid's shorter B suffix and overlap reduce completion despite similar row events. P3's win is small; it is specific to this seed/configuration. |
| A long slow prefix loses to B | **Survives for the legacy slow-A settings; changes with different service availability.** | Legacy N=32,S=24 hybrid loses to B in P1/P2/P3. With recommended A I=1 plus P2/P3 reservations, both N=32,S=8 and S=24 beat both baselines on all four traces. A larger prefix is not inherently bad; the balance depends on available A service and B setup. |
| A sufficiently slow sink makes all three modes tie | **Only the A/hybrid tie survives in the legacy slow-sink case.** | P2 A/H mean completion is 127 cycles and rate 0.0625; B-only mean is 130.891, p99 159 and rate 0.060656. B-only sees 95 completed closed-row setups and 66 maintenance starts in its measured window. Some delayed first words miss scheduled sink opportunities. Low average sink demand alone does not guarantee an exact tie. |
| Equal nominal aggregate rate makes hybrid lose to both | **Survives P1; changes to win-A/lose-B under P2/P3.** | P1 A/B/H = 0.842452/0.734873/0.589289. P2 = 0.316764/0.692053/0.461261. A's two-of-three reservation cuts its available service; the original hybrid interval-2 control is no longer an available-bandwidth match. Retain it as a supplementary nominal-input control, not proof at equal hardware resources or equal usable bandwidth. |
| Request skew produces only a three-cycle startup benefit | **Does not survive.** | New legacy overlays lose to B in steady state, and P2 loses to both. P2 hybrid mean request skew is 7.468 cycles and mean completion 33.532, versus A 32.999 and B 32.905. Jitter/maintenance shift later command edges and therefore future independent acceptance gates; the effect persists beyond startup. |

These mechanism explanations are inferences supported by configured timing, public-channel timestamps and row/grant/calendar counters. They are not a claim that one isolated mechanism accounts for every cycle without a further ablation.

## Recommended settings: where hybrid wins and loses

For sequential, early-on runs over six splits × four traces:

- **P1, quiet independent paths:** hybrid loses to A and beats B in all 24 triplets. With N=256,S=64, trace-median rates A/B/H are 0.977130/0.702332/0.875114. Full-rate resident SRAM is the better baseline in this experiment.
- **P2, reserved independent paths:** hybrid beats both for both 32-word splits on all four traces (eight triplets). N=256,S=64 beats A but loses to B on every trace. All 8-word splits lose to A; S=1 also loses to B on one trace.
- **P3, reserved shared return:** both 32-word splits again beat both on all four traces. N=256,S=64 beats A on all four, but wins against B on two and loses on two. The shared link constrains grants, so two memory resources do not imply twice the return bandwidth. Across the 24 sequential triplets, hybrid versus B is 19 wins / 1 tie / 4 losses; versus A is 12 wins / 0 ties / 12 losses.

The better baseline must be evaluated per paired trace. Medians across traces can conceal a loss on an individual trace. Primary counts are directed-case counts, not likelihood estimates.

## Locality, early delivery, and tails

For recommended P1 N=32,S=8, seed 11, permuting the same 128-block footprint increases completed B row conflicts from 128 to 856. B-only steady rate falls from 0.349410 to 0.294404; hybrid falls from 0.382759 to 0.318099. A-only is unchanged. At N=8, that same-footprint permutation rarely changes row state because the footprint maps to one resident row per bank. The separately labeled alternating-row and expanded-footprint workloads expose conflicts instead; they are not claimed to preserve the footprint. P1 N=8,S=3 alternating rows produces 1,024 measured conflicts and reduces B/hybrid rates to 0.092486/0.095688 (seed 11).

Early delivery remains useful but does not establish hybrid superiority by itself. In P2 N=32,S=8, seed 11, A/B/H rates with early delivery are 0.316764/0.343740/0.375010; gating on the whole block reduces them to 0.242424/0.250019/0.272728. Hybrid's mean first word moves from 7.046 to 85.333 cycles, and measured early-consumed words fall from 29,696 to zero. All modes receive the same control.

Better mean performance can coexist with worse tails. In recommended P2 N=8,S=3, seed 11, hybrid mean completion is 60.955 versus B-only 63.250, but hybrid p99 completion is **79 versus 76**. Hybrid p99 across the four traces ranges from 79 to 90 cycles. The report includes first-word/completion min, median, mean, p95, p99, max, per-trace rates, and 32-block rate variation; no confidence intervals are inferred from four schedules.

Doubling warmup/measurement changes one of 32 checked paired classifications. P3 N=8,S=3, sequential, early-on, seed 29: B/hybrid rates are 0.125017/0.125000 in the original window and 0.124993/0.125000 in the doubled window. This is a **fragile phase/window effect**, not evidence of a robust throughput advantage. The hybrid's mean first-word latency can also differ from A-only despite using the same A path, because command timing samples a different calendar phase.

## What changed in the implementation?

The new pair first accepts at most one descriptor per interface. Path latency/jitter and B row setup establish service eligibility. P1/P2 may grant both independent paths; P3 applies the shared reservation calendar and beat round robin. Each grant fills one registered response word. An existing response holds until handshake, regardless of later pauses. Only the final handshake releases its descriptor. The controller then follows its existing committed-word counts and synchronous read pipeline; no controller or bank changes were required.

The finite calendar advances every reset-relative clock, even when idle or stalled. Its saved representation contains every jitter sample and losslessly encoded periodic events. Shared reset restarts the calendar and cancels descriptors, row setup, held responses and controller output. Verification checks grants/ownership/capacity separately from the unchanged independent command-address data oracle.

No unresolved simulation, assertion or accounting failure remains in the executed matrix. Tested scope is finite: the model omits native HBM commands, overfetch, width conversion, deep queues and same-bank external interference. Entire source residency and excluded preload cost matter to A-only applicability. Physical synthesis, BRAM inference, timing closure and device operation remain untested. The matrix reduction and all limitations are documented; this is not completion of Stage 5 or Stage 4.

## Review questions and next decision

1. Why can a response handshake on a reserved transport edge still satisfy P3's shared bandwidth limit?
2. Why does P1's full-rate A baseline change the conclusion even though hybrid still delivers far earlier than B-only?
3. Why should the seed-29 ranking flip and the worse p99 case prevent a broad claim that hybrid is faster?