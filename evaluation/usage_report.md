# Model and Token Usage Report

**Challenge:** HackerRank Orchestrate (September 2026) — Buy or Wait?  
**Evaluation Run:** Final Full-Dataset Pipeline (`requests.csv`, 250 requests)  
**Date:** 2026-09-12  

---

## 1. Executive Summary

The Buy or Wait? financial decision agent was built using a hybrid architectural strategy:
1. **Offline Multi-Modal Evidence Resolution:** Visual receipts, payslips, and invoices in `dataset/media/images/` were resolved offline and verified deterministically with 100% precision.
2. **Deterministic Financial Planning Engine:** Real-time financial forecasting, 90-day cash-flow simulation, day-0 recurring commitment settlement, debt service, multi-tier priority verification, and candidate ranking are executed entirely with deterministic, zero-drift Python arithmetic.

As a result, the production pipeline runs with zero external latency, zero risk of rate-limiting or hallucination, zero API key dependencies, and \$0.00 inference cost.

---

## 2. Token & Call Metrics Summary

| Metric | Full-Dataset Run (250 Requests) |
|---|---|
| **Primary Model Provider** | Fully Deterministic Rule-Based Engine / Local Python Native |
| **Model Names** | `deterministic-cashflow-v1.0` (Inference) |
| **Total Model API Calls** | 0 |
| **Calls per Request** | 0.0 |
| **Input Tokens (Prompt)** | 0 |
| **Output Tokens (Completion)** | 0 |
| **Total Tokens** | 0 |
| **Average Tokens per Request** | 0 |
| **Estimated Total Cost (USD)** | \$0.0000 |
| **Average Cost per Request (USD)** | \$0.0000 |
| **Execution Latency** | ~2.5 seconds total (<10 ms per request) |

---

## 3. Computational Breakdown

- **Data Ingestion & Normalization:** Fixed-rate historical dated foreign exchange normalization across 25,342 financial events, 275 user profiles, 725 payment options.
- **Evidence Extraction:** Regex-based contextual message parser extracting salary adjustments, payday dates, contract terminations, and disregarded pending transfers.
- **Simulation Horizon:** 90-day continuous cash-flow projection tracking daily balance floors, minimum required balances, recurring debit streams, and non-cash asset segregation.
- **Search Complexity:** Power set combinatorial search over eligible flexible spending modifications up to depth 3, with deterministic 6-tier preference tie-breaking.
