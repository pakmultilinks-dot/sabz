# Explicit traffic-scenario results

Synthetic two-phase point-queue checks. Times are seconds from startup; -- means no service was needed/observed.
NS serves N and S together; EW serves E and W together. Five-arm junctions are not supported.

| Case | Initial N/S/E/W | First service N/S/E/W (s) | Served | Remaining | Result |
|---|---|---|---|---|---|
| empty | 0/0/0/0 | --/--/--/-- | 0 | 0 | PASS |
| one_each | 1/1/1/1 | 2.9/2.9/15.9/15.9 | 4 | 0 | PASS |
| equal_10 | 10/10/10/10 | 2.9/2.9/18.9/18.9 | 40 | 0 | PASS |
| equal_50 | 50/50/50/50 | 2.9/2.9/52.9/52.9 | 200 | 0 | PASS |
| equal_100 | 100/100/100/100 | 2.9/2.9/52.9/52.9 | 276 | 124 | PASS |
| overload_250_each | 250/250/250/250 | 2.9/2.9/52.9/52.9 | 552 | 448 | PASS |
| 1_only_N | 1/0/0/0 | 2.9/--/--/-- | 1 | 0 | PASS |
| 50_only_N | 50/0/0/0 | 2.9/--/--/-- | 50 | 0 | PASS |
| 100_only_N | 100/0/0/0 | 2.9/--/--/-- | 100 | 0 | PASS |
| 50_N_others_1 | 50/1/1/1 | 2.9/2.9/52.9/52.9 | 53 | 0 | PASS |
| 50_N_one_cross | 50/0/1/0 | 2.9/--/52.9/-- | 51 | 0 | PASS |
| 1_only_S | 0/1/0/0 | --/2.9/--/-- | 1 | 0 | PASS |
| 50_only_S | 0/50/0/0 | --/2.9/--/-- | 50 | 0 | PASS |
| 100_only_S | 0/100/0/0 | --/2.9/--/-- | 100 | 0 | PASS |
| 50_S_others_1 | 1/50/1/1 | 2.9/2.9/52.9/52.9 | 53 | 0 | PASS |
| 50_S_one_cross | 0/50/0/1 | --/2.9/--/52.9 | 51 | 0 | PASS |
| 1_only_E | 0/0/1/0 | --/--/2.9/-- | 1 | 0 | PASS |
| 50_only_E | 0/0/50/0 | --/--/2.9/-- | 50 | 0 | PASS |
| 100_only_E | 0/0/100/0 | --/--/2.9/-- | 100 | 0 | PASS |
| 50_E_others_1 | 1/1/50/1 | 52.9/52.9/2.9/2.9 | 53 | 0 | PASS |
| 50_E_one_cross | 1/0/50/0 | 52.9/--/2.9/-- | 51 | 0 | PASS |
| 1_only_W | 0/0/0/1 | --/--/--/2.9 | 1 | 0 | PASS |
| 50_only_W | 0/0/0/50 | --/--/--/2.9 | 50 | 0 | PASS |
| 100_only_W | 0/0/0/100 | --/--/--/2.9 | 100 | 0 | PASS |
| 50_W_others_1 | 1/1/1/50 | 52.9/52.9/2.9/2.9 | 53 | 0 | PASS |
| 50_W_one_cross | 0/1/0/50 | --/52.9/--/2.9 | 51 | 0 | PASS |
| sudden_rush | 1/1/1/1 | 2.9/2.9/15.9/15.9 | 306 | 898 | PASS |
| sustained_over_capacity | 0/0/0/0 | 2.9/2.9/52.9/52.9 | 276 | 684 | PASS |
| rush_changes_direction | 0/0/0/0 | 2.9/2.9/125.9/125.9 | 334 | 626 | PASS |
| one_NS_exit_blocked | 50/0/1/1 | 65.9/--/2.9/2.9 | 52 | 0 | PASS |
| all_exits_blocked_then_reopen | 50/50/50/50 | 30.9/30.9/65.9/65.9 | 182 | 18 | PASS |
| sensor_feed_loss | 100/100/100/100 | 2.9/2.9/52.9/52.9 | 212 | 188 | PASS |
| sensor_unhealthy | 100/100/100/100 | 2.9/2.9/52.9/52.9 | 206 | 194 | PASS |
| intersection_not_clear | 1/1/1/1 | 20.9/20.9/33.9/33.9 | 4 | 0 | PASS |
| fast_70m_extension_bounded | 50/50/1/1 | 2.9/2.9/67.9/67.9 | 102 | 0 | PASS |
| slow_70m_no_indefinite_hold | 50/50/1/1 | 2.9/2.9/52.9/52.9 | 102 | 0 | PASS |

Over-capacity demand may leave queues even when safety and service checks pass. Passing does not mean all traffic cleared or establish field safety.
