/* utils.js — shared formatting helpers for Customy dashboard */
window.CUtils = (function () {
  "use strict";

  function formatNumber(value) {
    var n = Number(value || 0);
    return Number.isFinite(n) ? n.toLocaleString() : "-";
  }

  function formatUsd(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) return "-";
    if (n === 0) return "$0.00";
    return "$" + n.toFixed(n < 0.01 ? 6 : 4);
  }

  function formatScore(value) {
    if (value === null || value === undefined || value === "") return "-";
    var n = Number(value);
    return Number.isFinite(n) ? n.toFixed(1) : "-";
  }

  return { formatNumber: formatNumber, formatUsd: formatUsd, formatScore: formatScore };
})();
