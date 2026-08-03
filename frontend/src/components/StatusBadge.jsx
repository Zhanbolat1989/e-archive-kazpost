const MAP = {
  uploaded: ["Загружен", "b-gray"],
  scanning: ["Антивирус…", "b-amber"],
  infected: ["⚠ Заражён", "b-red"],
  processing: ["Обработка…", "b-amber"],
  ready: ["Готов", "b-green"],
  failed: ["Ошибка", "b-red"],
};

const SIG = {
  none: null,
  valid: ["✔ ЭЦП верна", "b-green"],
  invalid: ["✖ ЭЦП неверна", "b-red"],
  unsupported: ["ЭЦП: ГОСТ", "b-gray"],
};

export function StatusBadge({ status }) {
  const [label, cls] = MAP[status] || [status, "b-gray"];
  const pulsing = status === "scanning" || status === "processing";
  return <span className={`badge ${cls} ${pulsing ? "pulse" : ""}`}>{label}</span>;
}

export function SignatureBadge({ status }) {
  const v = SIG[status];
  if (!v) return null;
  return <span className={`badge ${v[1]}`}>{v[0]}</span>;
}
