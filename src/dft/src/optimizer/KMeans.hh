// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2025, The OpenROAD Authors

#pragma once

#include <algorithm>
#include <cstdint>
#include <limits>
#include <vector>

#include "ScanCell.hh"
#include "odb/geom.h"

namespace dft {

// Partition `cells` into k spatial clusters using Lloyd's algorithm with
// deterministic farthest-point seeding.  Returns an assignment vector where
// assignments[i] is the cluster index in [0, k) for cells[i].
//
// Precondition: all cells must be placed (isPlaced() == true).
// Uses Manhattan distance throughout, consistent with the scan optimizer.
//
// Seeding is deterministic (farthest-point) rather than random so that
// OpenROAD runs remain reproducible across invocations.
//
// Degenerate cases:
//   k <= 1 or n <= k: all cells are assigned to cluster 0.
inline std::vector<int> KMeansClusters(const std::vector<ScanCell*>& cells,
                                        int k,
                                        int max_iters = 100)
{
  const int n = static_cast<int>(cells.size());

  if (k <= 1 || n <= k) {
    return std::vector<int>(n, 0);
  }

  // Cache cell origins once.
  std::vector<odb::Point> pts(n);
  for (int i = 0; i < n; i++) {
    pts[i] = cells[i]->getOrigin();
  }

  // ---------------------------------------------------------------------------
  // Farthest-point seeding: pick k initial centroids spread across the die.
  // The first centroid is cells[0] (arbitrary but deterministic).  Each
  // subsequent centroid is the cell whose Manhattan distance to the nearest
  // existing centroid is largest.
  // ---------------------------------------------------------------------------
  std::vector<odb::Point> centroids;
  centroids.reserve(k);
  centroids.push_back(pts[0]);

  // dist[i] = Manhattan distance from pts[i] to its nearest centroid so far.
  std::vector<int64_t> dist(n, std::numeric_limits<int64_t>::max());

  for (int c = 1; c < k; c++) {
    const odb::Point& new_cen = centroids.back();
    for (int i = 0; i < n; i++) {
      const int64_t d
          = std::abs(static_cast<int64_t>(pts[i].x()) - new_cen.x())
            + std::abs(static_cast<int64_t>(pts[i].y()) - new_cen.y());
      dist[i] = std::min(dist[i], d);
    }
    const int farthest = static_cast<int>(
        std::max_element(dist.begin(), dist.end()) - dist.begin());
    centroids.push_back(pts[farthest]);
  }

  // ---------------------------------------------------------------------------
  // Lloyd's algorithm: alternate assignment and centroid update until
  // convergence or max_iters is reached.
  // ---------------------------------------------------------------------------
  std::vector<int> assignments(n, 0);

  for (int iter = 0; iter < max_iters; iter++) {
    // Assignment step.
    bool changed = false;
    for (int i = 0; i < n; i++) {
      int best_c = 0;
      int64_t best_d = std::numeric_limits<int64_t>::max();
      for (int c = 0; c < k; c++) {
        const int64_t d
            = std::abs(static_cast<int64_t>(pts[i].x()) - centroids[c].x())
              + std::abs(static_cast<int64_t>(pts[i].y()) - centroids[c].y());
        if (d < best_d) {
          best_d = d;
          best_c = c;
        }
      }
      if (assignments[i] != best_c) {
        assignments[i] = best_c;
        changed = true;
      }
    }

    if (!changed) {
      break;  // Converged.
    }

    // Update step: recompute each centroid as the mean of its assigned cells.
    std::vector<int64_t> sum_x(k, 0), sum_y(k, 0);
    std::vector<int> count(k, 0);
    for (int i = 0; i < n; i++) {
      sum_x[assignments[i]] += pts[i].x();
      sum_y[assignments[i]] += pts[i].y();
      count[assignments[i]]++;
    }
    for (int c = 0; c < k; c++) {
      if (count[c] > 0) {
        centroids[c] = odb::Point(static_cast<int>(sum_x[c] / count[c]),
                                   static_cast<int>(sum_y[c] / count[c]));
      }
      // Empty cluster: keep previous centroid to avoid degenerate collapse.
    }
  }

  return assignments;
}

}  // namespace dft
