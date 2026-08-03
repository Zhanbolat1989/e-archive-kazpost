import { useState, useMemo } from "react";

// Дата → сравнимая метка времени (null для пустой) для accessor'ов сортировки.
export const dateKey = (d) => (d ? new Date(d).getTime() : null);

// Ранг «постоянного» срока хранения: конечное большое число, а не Infinity —
// иначе сравнение двух «постоянных» строк даёт Infinity−Infinity = NaN и
// неопределённый порядок в comparator'е.
export const PERMANENT_RANK = Number.MAX_SAFE_INTEGER;

// Общая сортировка таблиц для всех модулей. Один источник правды, чтобы
// поведение (стрелки, порядок, null-в-конце) было одинаковым везде.
//
// accessors: { ключ: (строка) => сравнимое_значение }. Число сравнивается как
// число, остальное — как строка через localeCompare("ru") (регистр/ё/дефисы).
// Пустые значения (null/""/undefined) всегда уходят в конец, независимо от
// направления — иначе клик по столбцу «прятал» бы заполненные строки под пустыми.
export function useSort(rows, accessors, initial = null) {
  const [key, setKey] = useState(initial?.key ?? null);
  const [dir, setDir] = useState(initial?.dir ?? "asc");

  function toggle(k) {
    if (k === key) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setKey(k);
      setDir("asc");
    }
  }

  const sorted = useMemo(() => {
    const get = key && accessors[key];
    if (!get) return rows; // без выбранного столбца — исходный порядок API
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = get(a);
      const bv = get(b);
      const aEmpty = av == null || av === "";
      const bEmpty = bv == null || bv === "";
      if (aEmpty && bEmpty) return 0;
      if (aEmpty) return 1;
      if (bEmpty) return -1;
      const base =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv), "ru");
      return dir === "asc" ? base : -base;
    });
    return copy;
  }, [rows, key, dir, accessors]);

  return { sorted, key, dir, toggle };
}

// Кликабельный заголовок столбца со стрелкой направления.
export function SortTh({ label, sortKey, sort, className = "" }) {
  const active = sort.key === sortKey;
  return (
    <th
      className={`sortable ${active ? "sorted" : ""} ${className}`.trim()}
      onClick={() => sort.toggle(sortKey)}
      title="Сортировать по столбцу"
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
    >
      {label}
      <span className="sort-arrow">{active ? (sort.dir === "asc" ? "▲" : "▼") : "⇅"}</span>
    </th>
  );
}
