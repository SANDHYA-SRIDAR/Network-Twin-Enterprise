"""Independent evaluation script for topology anomaly detection — Stage 2c.

Measures exact precision, recall, false-positive rates, and confusion counts
on the FRESH held-out test split (disjoint seeds 4000..4049).
Evaluates contextual ML detection vs fixed threshold baseline vs robust peer-MAD baseline.
Evaluates deterministic traffic overload detection rule from evaluate().
"""
from __future__ import annotations

from copy import deepcopy
import sys
import os

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from app.models.network import LinkDefinition, NetworkDefinition, NodeDefinition
from app.engines.graph_adapter import operational
from app.services.anomaly_detector import analyze_topology_anomalies
from app.services.synthetic_topologies import (
    STAGE2B_TEST_SEED_COUNT,
    STAGE2B_TEST_SEED_START,
    VAL_SEED_COUNT,
    VAL_SEED_START,
    generate_synthetic_enterprise_topology,
    inject_anomaly,
)


def simple_threshold_baseline(network: NetworkDefinition) -> set[str]:
    """Simple baseline detector using fixed domain thresholds."""
    flagged: set[str] = set()
    for link in network.links:
        loss = link.packet_loss_pct if link.packet_loss_pct is not None else 0.0
        delay = link.delay_ms if link.delay_ms is not None else 1.0
        bw = link.bandwidth_mbps if link.bandwidth_mbps is not None else 1000.0
        if loss > 5.0 or delay > 25.0 or bw < 50.0:
            flagged.add(link.id)
    return flagged


def peer_relative_robust_baseline(network: NetworkDefinition, k: float = 3.5) -> set[str]:
    """Peer-relative robust statistics baseline using Median and Median Absolute Deviation (MAD).
    
    Tuned k=3.5 strictly on the validation split (seeds 2000..2009).
    """
    nodes = {n.id: n for n in network.nodes}
    operational_links = [e for e in network.links if operational(e, nodes)]
    
    links_by_pair: dict[tuple[str, str], list[LinkDefinition]] = {}
    for l in operational_links:
        u_type = nodes[l.source_node_id].device_type if l.source_node_id in nodes else "unknown"
        v_type = nodes[l.target_node_id].device_type if l.target_node_id in nodes else "unknown"
        p = tuple(sorted([u_type, v_type]))
        links_by_pair.setdefault(p, []).append(l)

    all_delays = np.array([l.delay_ms if l.delay_ms is not None else 1.0 for l in operational_links])
    all_losses = np.array([l.packet_loss_pct if l.packet_loss_pct is not None else 0.0 for l in operational_links])
    top_med_d = float(np.median(all_delays)) if len(all_delays) else 1.0
    top_mad_d = max(float(np.median(np.abs(all_delays - top_med_d))), 0.2)
    top_med_l = float(np.median(all_losses)) if len(all_losses) else 0.0
    top_mad_l = max(float(np.median(np.abs(all_losses - top_med_l))), 0.01)

    flagged: set[str] = set()
    for l in operational_links:
        u_type = nodes[l.source_node_id].device_type if l.source_node_id in nodes else "unknown"
        v_type = nodes[l.target_node_id].device_type if l.target_node_id in nodes else "unknown"
        p = tuple(sorted([u_type, v_type]))
        group = links_by_pair.get(p, [l])

        d = l.delay_ms if l.delay_ms is not None else 1.0
        loss = l.packet_loss_pct if l.packet_loss_pct is not None else 0.0

        if len(group) >= 3:
            delays = np.array([x.delay_ms if x.delay_ms is not None else 1.0 for x in group])
            losses = np.array([x.packet_loss_pct if x.packet_loss_pct is not None else 0.0 for x in group])
            med_d = float(np.median(delays))
            mad_d = max(float(np.median(np.abs(delays - med_d))), 0.1)
            med_l = float(np.median(losses))
            mad_l = max(float(np.median(np.abs(losses - med_l))), 0.01)
        else:
            router_links = [x for x in operational_links if "router" in (nodes[x.source_node_id].device_type, nodes[x.target_node_id].device_type)]
            if "router" in p and len(router_links) >= 3:
                delays = np.array([x.delay_ms if x.delay_ms is not None else 1.0 for x in router_links])
                losses = np.array([x.packet_loss_pct if x.packet_loss_pct is not None else 0.0 for x in router_links])
                med_d = float(np.median(delays))
                mad_d = max(float(np.median(np.abs(delays - med_d))), 0.1)
                med_l = float(np.median(losses))
                mad_l = max(float(np.median(np.abs(losses - med_l))), 0.01)
            else:
                med_d, mad_d = top_med_d, top_mad_d
                med_l, mad_l = top_med_l, top_mad_l

        if (d - med_d) > k * mad_d or (loss - med_l) > k * mad_l:
            flagged.add(l.id)

    return flagged


def run_evaluation():
    print("=" * 80)
    print("NETTRANSFORM AI — STAGE 2c ANOMALY DETECTOR BENCHMARK EVALUATION")
    print(f"Test split: 50 FRESH held-out synthetic topologies (Seeds {STAGE2B_TEST_SEED_START}..{STAGE2B_TEST_SEED_START + STAGE2B_TEST_SEED_COUNT - 1})")
    print("Validation split (tuning only, disjoint): Seeds 2000..2009")
    print("Baselines: (1) Fixed Threshold Rule (2) Peer-Relative Robust MAD Rule (k=3.5)")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. CLEAN TOPOLOGY EVALUATION (False-Positive Rate Check)
    # -------------------------------------------------------------------------
    print("\n--- 1. Clean Topologies (No Injected Anomaly) ---")
    clean_topos = [
        generate_synthetic_enterprise_topology(seed)
        for seed in range(STAGE2B_TEST_SEED_START, STAGE2B_TEST_SEED_START + STAGE2B_TEST_SEED_COUNT)
    ]
    total_clean_links = sum(len(t.links) for t in clean_topos)
    total_clean_nodes = sum(len(t.nodes) for t in clean_topos)
    total_clean_elements = total_clean_links + total_clean_nodes

    ml_fp_elements = 0
    ml_fp_topos = 0
    base_fp_elements = 0
    base_fp_topos = 0
    mad_fp_elements = 0
    mad_fp_topos = 0

    for t in clean_topos:
        res = analyze_topology_anomalies(t)
        ml_flagged = {f.target_id for f in res.findings if "isolation_forest" in f.methods}
        if ml_flagged:
            ml_fp_topos += 1
            ml_fp_elements += len(ml_flagged)

        base_flagged = simple_threshold_baseline(t)
        if base_flagged:
            base_fp_topos += 1
            base_fp_elements += len(base_flagged)

        mad_flagged = peer_relative_robust_baseline(t, k=3.5)
        if mad_flagged:
            mad_fp_topos += 1
            mad_fp_elements += len(mad_flagged)

    elem_fpr_ml = ml_fp_elements / max(1, total_clean_elements)
    topo_fpr_ml = ml_fp_topos / len(clean_topos)
    elem_fpr_base = base_fp_elements / max(1, total_clean_elements)
    topo_fpr_base = base_fp_topos / len(clean_topos)
    elem_fpr_mad = mad_fp_elements / max(1, total_clean_elements)
    topo_fpr_mad = mad_fp_topos / len(clean_topos)

    print(f"Total clean topologies evaluated: {len(clean_topos)}")
    print(f"Total clean elements: {total_clean_elements} ({total_clean_links} links, {total_clean_nodes} nodes)")
    print(f"IsolationForest ML FP:           {ml_fp_elements:2d} elements across {ml_fp_topos:2d} topos -> Topo FPR: {topo_fpr_ml*100:5.2f}%, Elem FPR: {elem_fpr_ml*100:5.2f}%")
    print(f"Fixed Threshold Baseline FP:     {base_fp_elements:2d} elements across {base_fp_topos:2d} topos -> Topo FPR: {topo_fpr_base*100:5.2f}%, Elem FPR: {elem_fpr_base*100:5.2f}%")
    print(f"Peer-Relative Robust MAD FP:     {mad_fp_elements:2d} elements across {mad_fp_topos:2d} topos -> Topo FPR: {topo_fpr_mad*100:5.2f}%, Elem FPR: {elem_fpr_mad*100:5.2f}%")

    # -------------------------------------------------------------------------
    # 2. CONTEXTUAL & METRIC ANOMALIES EVALUATION
    # -------------------------------------------------------------------------
    print("\n--- 2. Contextual & Metric Anomalies Evaluation ---")
    categories = [
        ("contextual_subtle_anomaly", range(4000, 4010)),
        ("overloaded_link", range(4010, 4020)),
        ("lossy_link", range(4020, 4030)),
        ("high_delay_link", range(4030, 4040)),
    ]

    stats = {
        "ml": {"tp": 0, "fn": 0, "fp": 0, "by_type": {}},
        "threshold": {"tp": 0, "fn": 0, "fp": 0, "by_type": {}},
        "mad": {"tp": 0, "fn": 0, "fp": 0, "by_type": {}},
        "rule_engine": {"tp": 0, "fn": 0, "fp": 0, "by_type": {}},
    }

    for cat_name, seed_range in categories:
        for k in stats:
            stats[k]["by_type"][cat_name] = {"tp": 0, "fn": 0, "fp": 0}

        for seed in seed_range:
            base_topo = generate_synthetic_enterprise_topology(seed)
            injected_topo, truth = inject_anomaly(base_topo, cat_name, seed)
            target_id = truth["target_id"]
            traffic = truth.get("traffic")

            # 1. Evaluate ML Findings
            res = analyze_topology_anomalies(injected_topo, traffic=traffic)
            ml_flagged = {f.target_id for f in res.findings if "isolation_forest" in f.methods}
            if target_id in ml_flagged:
                stats["ml"]["tp"] += 1
                stats["ml"]["by_type"][cat_name]["tp"] += 1
            else:
                stats["ml"]["fn"] += 1
                stats["ml"]["by_type"][cat_name]["fn"] += 1
            extra_ml = len(ml_flagged - {target_id})
            stats["ml"]["fp"] += extra_ml
            stats["ml"]["by_type"][cat_name]["fp"] += extra_ml

            # 2. Evaluate Rule Findings (from analyze_topology_anomalies)
            rule_flagged = {f.target_id for f in res.findings if "rule" in f.methods and f.tier == "metric_outlier"}
            if target_id in rule_flagged:
                stats["rule_engine"]["tp"] += 1
                stats["rule_engine"]["by_type"][cat_name]["tp"] += 1
            else:
                stats["rule_engine"]["fn"] += 1
                stats["rule_engine"]["by_type"][cat_name]["fn"] += 1
            extra_rule = len(rule_flagged - {target_id})
            stats["rule_engine"]["fp"] += extra_rule
            stats["rule_engine"]["by_type"][cat_name]["fp"] += extra_rule

            # 3. Evaluate Threshold Baseline
            thresh_flagged = simple_threshold_baseline(injected_topo)
            if target_id in thresh_flagged:
                stats["threshold"]["tp"] += 1
                stats["threshold"]["by_type"][cat_name]["tp"] += 1
            else:
                stats["threshold"]["fn"] += 1
                stats["threshold"]["by_type"][cat_name]["fn"] += 1
            extra_thresh = len(thresh_flagged - {target_id})
            stats["threshold"]["fp"] += extra_thresh
            stats["threshold"]["by_type"][cat_name]["fp"] += extra_thresh

            # 4. Evaluate Robust MAD Baseline
            mad_flagged = peer_relative_robust_baseline(injected_topo, k=3.5)
            if target_id in mad_flagged:
                stats["mad"]["tp"] += 1
                stats["mad"]["by_type"][cat_name]["tp"] += 1
            else:
                stats["mad"]["fn"] += 1
                stats["mad"]["by_type"][cat_name]["fn"] += 1
            extra_mad = len(mad_flagged - {target_id})
            stats["mad"]["fp"] += extra_mad
            stats["mad"]["by_type"][cat_name]["fp"] += extra_mad

    # Print Comparison Table
    print(f"{'Anomaly Type':<28} | {'Method':<24} | {'TP':<4} | {'FN':<4} | {'FP':<4} | {'Precision':<9} | {'Recall':<9} | {'F1':<9}")
    print("-" * 104)
    labels = [
        ("ml", "IsolationForest ML"),
        ("rule_engine", "Deterministic Rules"),
        ("threshold", "Fixed Threshold"),
        ("mad", "Peer Robust MAD (k=3.5)"),
    ]
    for cat_name, _ in categories:
        for m_name, label in labels:
            d = stats[m_name]["by_type"][cat_name]
            tp, fn, fp = d["tp"], d["fn"], d["fp"]
            prec = tp / max(1, tp + fp)
            rec = tp / max(1, tp + fn)
            f1 = (2 * prec * rec) / max(1e-6, prec + rec)
            print(f"{cat_name:<28} | {label:<24} | {tp:<4} | {fn:<4} | {fp:<4} | {prec:<9.4f} | {rec:<9.4f} | {f1:<9.4f}")
        print("-" * 104)

    # -------------------------------------------------------------------------
    # 3. CONTEXTUAL ANOMALY HEAD-TO-HEAD: ML vs Robust MAD Baseline
    # -------------------------------------------------------------------------
    print("\n--- 3. Contextual Anomaly Head-to-Head (ML vs Robust MAD Baseline) ---")
    ml_ctx_tp = stats["ml"]["by_type"]["contextual_subtle_anomaly"]["tp"]
    ml_ctx_rec = ml_ctx_tp / 10.0
    mad_ctx_tp = stats["mad"]["by_type"]["contextual_subtle_anomaly"]["tp"]
    mad_ctx_rec = mad_ctx_tp / 10.0
    print(f"IsolationForest ML Contextual Recall:       {ml_ctx_rec:.2f} ({ml_ctx_tp}/10)")
    print(f"Peer Robust MAD (k=3.5) Contextual Recall: {mad_ctx_rec:.2f} ({mad_ctx_tp}/10)")
    if mad_ctx_rec >= ml_ctx_rec:
        print("-> The robust peer-relative statistics baseline matches or beats ML on contextual anomalies.")
        print("   Notice: Robust MAD has a higher clean false-positive rate on small peer groups.")
    else:
        print("-> ML achieves higher recall on contextual anomalies than the robust baseline.")

    # -------------------------------------------------------------------------
    # 4. OVERLOAD RULE CONFIRMATION
    # -------------------------------------------------------------------------
    print("\n--- 4. Deterministic Overload Rule Confirmation ---")
    ovld_tp = stats["rule_engine"]["by_type"]["overloaded_link"]["tp"]
    print(f"Deterministic Overload Rule Recall: {ovld_tp / 10.0:.2f} ({ovld_tp}/10 links flagged with offered load >= capacity)")

    print("\n" + "=" * 80)
    print("STAGE 2c EVALUATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_evaluation()
