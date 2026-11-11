# Project record

## Objective

Provide an offline Python library and CLI that turn exported Kubernetes usage samples into CPU and memory requests and limits using nearest-rank percentiles, integer margin/step/floor math, documented quantity parsing and YAML patch rendering.

## Scope

In scope:

- `parse_quantity` for the documented Kubernetes resource.Quantity subset.
- `read_samples_csv` for CSV streams with the required columns.
- `Policy`-controlled recommendation math in `recommend`.
- `assess` against current requests.
- `render_patch` and the `k8s-resource-advisor` CLI.

Out of scope:

- Reading the Kubernetes Metrics API or Prometheus.
- HPA or VPA interplay and cluster controllers.
- Applying patches to a cluster.
- Node packing or capacity planning.

## Timeline

| Date | Event |
|---|---|
| Not recorded | The repository does not include a changelog or dated project history. |

## Effort metrics

| Metric | Value |
|---|---|
| Tokens (input / output) | 671337 / 67965 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.0959 |

## Factory run u284 (measured from API usage)

| Date (UTC) | Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| 2026-11-10 | generation | deepseek-v4-pro | yes | 1828 | 22594 | 0 | 3200 | 0.0460 |
| 2026-11-10 | fix-1 | deepseek-flash | no | 11519 | 6595 | 0 | 84864 | 0.0059 |
| 2026-11-10 | fix-2 | deepseek-flash | no | 9910 | 3326 | 0 | 68864 | 0.0037 |
| 2026-11-10 | audit | deepseek-flash | no | 18971 | 18085 | 0 | 297344 | 0.0146 |
| 2026-11-10 | fix-3 | deepseek-flash | no | 10091 | 4032 | 0 | 74624 | 0.0042 |
| 2026-11-10 | docs | deepseek-flash | no | 89866 | 13333 | 0 | 256 | 0.0215 |

Total: $0.0959. Prices: deepseek line, as measured by its adapter. Providers serve the current version of each model id, so the date tells which version answered; versions, launch stages and price sources per line are in the factory's model register (docs/MODELS.md).
