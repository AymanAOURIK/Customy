/* utils.js — shared formatting helpers for Customy dashboard */
window.CUtils = (function () {
  "use strict";

  function toFiniteNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    var text = typeof value === "string" ? value.replace(/,/g, "").trim() : value;
    if (text === "") return null;
    var n = Number(text);
    return Number.isFinite(n) ? n : null;
  }

  function formatNumber(value) {
    var n = toFiniteNumber(value);
    if (n === null) {
      return value === null || value === undefined || value === "" ? "0" : "-";
    }
    return n.toLocaleString();
  }

  function formatUsd(value) {
    var n = toFiniteNumber(value);
    if (n === null) return "-";
    if (n === 0) return "$0.00";
    return "$" + n.toFixed(n < 0.01 ? 6 : 4);
  }

  function formatScore(value) {
    var n = toFiniteNumber(value);
    return n === null ? "-" : n.toFixed(1);
  }

  return {
    toFiniteNumber: toFiniteNumber,
    formatNumber: formatNumber,
    formatUsd: formatUsd,
    formatScore: formatScore,
  };
})();
