# Stage 9.1: Attack Quality, Deduplication & Prioritization Hardening

## Attack Quality
Attack count alone is insufficient for robust verification. A high volume of redundant or low-value attacks simply consumes resources without exposing new behaviors. Stage 9.1 introduces deterministic quality scoring that considers novelty, boundary relevance, task relevance, and oracle strength, ensuring REDLINE maximizes its verification value per unit of budget.

## Prioritization
REDLINE ranks attacks deterministically using a transparent formula. It assigns values to oracle strength, risk level, category (with SECURITY and RESOURCE attacks prioritized), and penalizes redundancy and cost. Model confidence is treated as untrusted metadata and cannot override deterministic scoring.

## Budget
Finite attack budgets are explicitly enforced. The orchestrator specifies the maximum number of attack cases, and the selection algorithm respects this limit by selecting only the highest-scoring attacks.

## Redundancy
Redundant attacks are identified conservatively to prevent dropping valuable distinct tests. A `redundancy_group` is computed based on `attack_type` and `target`. When multiple attacks share the same group, they incur an increasing redundancy penalty, encouraging the selector to explore other areas of the system if alternatives exist.

## Diversity
Category diversity influences selection by applying a slight penalty for each existing attack selected from the same category. This ensures that while high-value security attacks still get prioritized, REDLINE won't blindly spend its entire budget on a single category if other categories offer reasonably valuable attacks.

## Determinism
Repeated identical inputs produce identical selection. The algorithm uses a stable tie-breaking hierarchy (Total Score -> Oracle Strength -> Relevance -> Novelty -> Category Priority -> Deterministic Fingerprint), ensuring that variations in model response time or dictionary ordering do not affect selection.

## Limitations
Real-world execution benchmarking is deferred until a secure untrusted-repository sandbox backend is available. Currently, only the benchmark foundation (data structures and selection evaluation logic) is implemented.
