const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
p.author = "e-archive";
p.title = "e-archive — Руководство пользователя";

// ---------- palette (matches the app's own design system) ----------
const NAVY = "202D3D", NAVYD = "13262F", GREEN = "23D292", GREEND = "18A872",
      CORAL = "FF8562", LIGHT = "F0F4F9", INK = "202D3D", WHITE = "FFFFFF",
      MUTED = "5C6672", TINTG = "E7F8F0", TINTN = "E9EEF4";
const HEAD = "Calibri", BODY = "Calibri", MONO = "Consolas";
const W = 13.33, H = 7.5, MX = 0.62, CW = W - MX * 2;

const sh = (o = {}) => Object.assign({ type: "outer", color: "202D3D", opacity: 0.16, blur: 9, offset: 3, angle: 90 }, o);

function kicker(s, txt, x, y, col = GREEN) {
  s.addText(txt.toUpperCase(), { x, y, w: 8, h: 0.3, fontFace: HEAD, fontSize: 12,
    bold: true, color: col, charSpacing: 2, margin: 0 });
}
function title(s, txt, x, y, col = INK, w = CW, size = 32) {
  s.addText(txt, { x, y, w, h: 0.75, fontFace: HEAD, fontSize: size, bold: true,
    color: col, margin: 0 });
}
function card(s, x, y, w, h, fill = WHITE, radius = 0.1) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: radius,
    fill: { color: fill }, line: { color: "E4E9F0", width: 1 }, shadow: sh() });
}
function pageNum(s, n) {
  s.addText(String(n).padStart(2, "0"), { x: W - 0.9, y: H - 0.5, w: 0.5, h: 0.3,
    fontFace: MONO, fontSize: 10, color: "AEB8C4", margin: 0, align: "right" });
}
function header(s, kick, ttl, dark = false) {
  kicker(s, kick, MX, 0.5, dark ? GREEN : GREEN);
  title(s, ttl, MX, 0.85, dark ? WHITE : INK);
}

// ---------- small vector nav-icon glyphs (echo the app's own sidebar icons) ----------
function iconChip(s, x, y, d, kind, bg = GREEN, fg = NAVYD) {
  s.addShape(p.ShapeType.roundRect, { x, y, w: d, h: d, rectRadius: d * 0.28,
    fill: { color: bg }, shadow: sh() });
  const pad = d * 0.27, ix = x + pad, iy = y + pad, iw = d - pad * 2;
  const ln = (x1, y1, x2, y2, wgt = 1.6) => s.addShape(p.ShapeType.line,
    { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001,
      h: Math.abs(y2 - y1) || 0.001, line: { color: fg, width: wgt } });
  const rect = (rx, ry, rw, rh, radius = 0.02) => s.addShape(p.ShapeType.roundRect,
    { x: rx, y: ry, w: rw, h: rh, rectRadius: radius, fill: { type: "none" }, line: { color: fg, width: 1.6 } });
  switch (kind) {
    case "dashboard":
      rect(ix, iy, iw * 0.42, iw * 0.55); rect(ix + iw * 0.56, iy, iw * 0.44, iw * 0.3);
      rect(ix + iw * 0.56, iy + iw * 0.42, iw * 0.44, iw * 0.58); rect(ix, iy + iw * 0.68, iw * 0.42, iw * 0.32);
      break;
    case "document":
      rect(ix + iw * 0.12, iy, iw * 0.62, iw); ln(ix + iw * 0.22, iy + iw * 0.35, ix + iw * 0.6, iy + iw * 0.35, 1.2);
      ln(ix + iw * 0.22, iy + iw * 0.55, ix + iw * 0.6, iy + iw * 0.55, 1.2);
      ln(ix + iw * 0.22, iy + iw * 0.75, ix + iw * 0.48, iy + iw * 0.75, 1.2);
      break;
    case "folder":
      s.addShape(p.ShapeType.roundRect, { x: ix, y: iy + iw * 0.18, w: iw, h: iw * 0.72, rectRadius: 0.02,
        fill: { type: "none" }, line: { color: fg, width: 1.6 } });
      ln(ix + iw * 0.06, iy + iw * 0.18, ix + iw * 0.4, iy + iw * 0.18, 1.6);
      ln(ix + iw * 0.4, iy + iw * 0.18, ix + iw * 0.5, iy + iw * 0.05, 1.6);
      ln(ix + iw * 0.5, iy + iw * 0.05, ix + iw * 0.86, iy + iw * 0.05, 1.6);
      ln(ix + iw * 0.86, iy + iw * 0.05, ix + iw * 0.94, iy + iw * 0.18, 1.6);
      break;
    case "list":
      [0.12, 0.45, 0.78].forEach((f) => ln(ix + iw * 0.28, iy + iw * f, ix + iw, iy + iw * f, 1.6));
      [0.12, 0.45, 0.78].forEach((f) => s.addShape(p.ShapeType.ellipse,
        { x: ix, y: iy + iw * f - 0.03, w: 0.06, h: 0.06, fill: { color: fg } }));
      break;
    case "issue":
      rect(ix, iy + iw * 0.12, iw * 0.42, iw * 0.76); ln(ix + iw * 0.34, iy + iw * 0.5, ix + iw, iy + iw * 0.5, 1.6);
      ln(ix + iw * 0.72, iy + iw * 0.22, ix + iw, iy + iw * 0.5, 1.6); ln(ix + iw * 0.72, iy + iw * 0.78, ix + iw, iy + iw * 0.5, 1.6);
      break;
    case "trash":
      ln(ix, iy + iw * 0.24, ix + iw, iy + iw * 0.24, 1.6);
      rect(ix + iw * 0.28, iy + iw * 0.24, iw * 0.44, iw * 0.68);
      ln(ix + iw * 0.36, iy, ix + iw * 0.64, iy, 1.6);
      break;
    case "bot":
      rect(ix, iy + iw * 0.28, iw, iw * 0.65); ln(ix + iw * 0.5, iy, ix + iw * 0.5, iy + iw * 0.28, 1.4);
      s.addShape(p.ShapeType.ellipse, { x: ix + iw * 0.28, y: iy + iw * 0.52, w: 0.06, h: 0.06, fill: { color: fg } });
      s.addShape(p.ShapeType.ellipse, { x: ix + iw * 0.66, y: iy + iw * 0.52, w: 0.06, h: 0.06, fill: { color: fg } });
      break;
    case "upload":
      ln(ix + iw * 0.5, iy + iw * 0.05, ix + iw * 0.5, iy + iw * 0.65, 1.6);
      ln(ix + iw * 0.22, iy + iw * 0.32, ix + iw * 0.5, iy + iw * 0.05, 1.6);
      ln(ix + iw * 0.78, iy + iw * 0.32, ix + iw * 0.5, iy + iw * 0.05, 1.6);
      ln(ix, iy + iw, ix + iw, iy + iw, 1.6);
      break;
  }
}

// ============================================================ 1. COVER
(() => {
  const s = p.addSlide();
  s.background = { color: NAVY };
  s.addShape(p.ShapeType.roundRect, { x: MX, y: 0.95, w: 0.85, h: 0.85, rectRadius: 0.15, fill: { color: GREEN } });
  s.addText("e", { x: MX, y: 0.95, w: 0.85, h: 0.85, align: "center", valign: "middle",
    fontFace: HEAD, fontSize: 42, bold: true, color: NAVYD, margin: 0 });
  s.addText("e-archive", { x: 1.62, y: 1.03, w: 8, h: 0.7, fontFace: HEAD, fontSize: 30,
    bold: true, color: WHITE, margin: 0, valign: "middle" });

  s.addText("Руководство пользователя", { x: MX, y: 2.75, w: 11.5, h: 0.9,
    fontFace: HEAD, fontSize: 42, bold: true, color: WHITE, margin: 0 });
  s.addText("Как работать в электронном архиве: от приёма документа до передачи дела в госархив",
    { x: MX, y: 3.65, w: 10.8, h: 0.6, fontFace: BODY, fontSize: 17, color: "C7D2DE", margin: 0 });

  const roles = ["Архивариус", "Администратор", "Читатель"];
  roles.forEach((r, i) => {
    const x = MX + i * 2.7;
    s.addShape(p.ShapeType.roundRect, { x, y: 4.7, w: 2.45, h: 0.55, rectRadius: 0.28,
      fill: { type: "none" }, line: { color: "3A4A5E", width: 1.2 } });
    s.addText(r, { x, y: 4.7, w: 2.45, h: 0.55, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 13, bold: true, color: "C7D2DE", margin: 0 });
  });

  s.addText("Версия для сотрудников архива · 2026", { x: MX, y: 6.6, w: 8, h: 0.35,
    fontFace: HEAD, fontSize: 12, bold: true, color: "8A98A8", charSpacing: 1, margin: 0 });
  s.addNotes("Руководство пользователя e-archive: практическое пособие для архивариуса. 12 слайдов, утилитарный стиль в фирменной палитре приложения.");
})();

// ============================================================ 2. НАВИГАЦИЯ
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Начало работы", "Навигация приложения");
  s.addText("После входа (email и пароль) слева — постоянное меню разделов. Каждый значок открывает свой раздел работы с архивом.",
    { x: MX, y: 1.55, w: CW, h: 0.5, fontFace: BODY, fontSize: 14.5, color: MUTED, margin: 0 });

  const items = [
    ["dashboard", "Дашборд", "Сводка: документы, обязательства/оплачено, сроки хранения"],
    ["document", "Документы", "Полный каталог с фильтрами и карточкой каждого документа"],
    ["folder", "Дела", "Единицы хранения: группировка документов, нормативные формы"],
    ["list", "Номенклатура", "Справочник статей со сроками хранения по перечню 279-НҚ"],
    ["issue", "Выдача", "Заказ дела во временное пользование, контроль возврата"],
    ["trash", "Уничтожение", "Истёкшие сроки → акт о выделении → утверждение"],
    ["bot", "ИИ-ассистент", "Диалог: вопросы по содержимому и по метаданным"],
    ["upload", "Приём", "Загрузка нового документа в архив"],
  ];
  const cols = 4, gap = 0.34, cw = (CW - gap * (cols - 1)) / cols, ch = 1.95, d = 0.62;
  items.forEach(([icon, t, desc], i) => {
    const r = Math.floor(i / cols), c = i % cols;
    const x = MX + c * (cw + gap), y = 2.35 + r * (ch + 0.3);
    card(s, x, y, cw, ch);
    iconChip(s, x + 0.24, y + 0.24, d, icon);
    s.addText(t, { x: x + 0.24, y: y + 1.0, w: cw - 0.45, h: 0.35, fontFace: HEAD,
      fontSize: 14.5, bold: true, color: INK, margin: 0 });
    s.addText(desc, { x: x + 0.24, y: y + 1.32, w: cw - 0.45, h: 0.55, fontFace: BODY,
      fontSize: 10.8, color: MUTED, margin: 0, lineSpacingMultiple: 1.05 });
  });
  pageNum(s, 2);
})();

// ============================================================ 3. ДАШБОРД
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Раздел «Дашборд»", "Что видно на главном экране");
  s.addText("Стартовая страница — сводка по всему архиву без единого клика: сколько документов, кто и сколько должен, что истекает.",
    { x: MX, y: 1.55, w: 6.6, h: 1.0, fontFace: BODY, fontSize: 14.5, color: MUTED, margin: 0, lineSpacingMultiple: 1.15 });

  const rows = [
    ["KPI-плашки", "Всего документов · обязательства · оплачено (%) · остаток к оплате"],
    ["Обязательства vs оплачено", "По каждому контрагенту: полоса прогресса и статус — закрыто / частично / не оплачено"],
    ["По типам документов", "Разбивка каталога по видам — сразу видно, чего накопилось больше всего"],
    ["Сроки хранения", "Список документов с истёкшим или истекающим (12 мес.) сроком — сигнал идти в «Уничтожение»"],
    ["Оплата по годам", "Столбцы платежей по календарным годам"],
  ];
  rows.forEach(([t, d], i) => {
    const y = 2.75 + i * 0.78;
    s.addShape(p.ShapeType.ellipse, { x: MX, y: y + 0.06, w: 0.13, h: 0.13, fill: { color: GREEN } });
    s.addText(t, { x: MX + 0.3, y: y - 0.08, w: 6.1, h: 0.32, fontFace: HEAD, fontSize: 13.5, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: MX + 0.3, y: y + 0.24, w: 6.1, h: 0.5, fontFace: BODY, fontSize: 11.5, color: MUTED, margin: 0, lineSpacingMultiple: 1.05 });
  });

  // mock dashboard panel on the right
  const rx = 7.3, rw = 5.4, ry = 1.55, rh = 5.35;
  card(s, rx, ry, rw, rh, WHITE, 0.14);
  s.addText("СВОДКА ПО АРХИВУ", { x: rx + 0.3, y: ry + 0.22, w: rw - 0.6, h: 0.25, fontFace: HEAD,
    fontSize: 10, bold: true, color: GREEND, charSpacing: 1.5, margin: 0 });
  const kpis = [["33", "документов"], ["27,6 млн ₸", "обязательства"], ["24,7 млн ₸", "оплачено · 90%"], ["2,9 млн ₸", "остаток"]];
  kpis.forEach(([v, l], i) => {
    const kx = rx + 0.3 + (i % 2) * ((rw - 0.6) / 2);
    const ky = ry + 0.6 + Math.floor(i / 2) * 0.85;
    s.addText(v, { x: kx, y: ky, w: (rw - 0.6) / 2 - 0.1, h: 0.4, fontFace: HEAD, fontSize: 17, bold: true, color: INK, margin: 0 });
    s.addText(l, { x: kx, y: ky + 0.36, w: (rw - 0.6) / 2 - 0.1, h: 0.3, fontFace: BODY, fontSize: 9.5, color: MUTED, margin: 0 });
  });
  s.addShape(p.ShapeType.line, { x: rx + 0.3, y: ry + 2.3, w: rw - 0.6, h: 0, line: { color: "E4E9F0", width: 1 } });
  s.addText("Обязательства vs оплачено", { x: rx + 0.3, y: ry + 2.42, w: rw - 0.6, h: 0.3, fontFace: HEAD, fontSize: 11, bold: true, color: INK, margin: 0 });
  const bars = [["ТОО «Кагаз Логистик»", 1.0, "Закрыто"], ["ИП Сериков А.Б.", 0.7, "Частично"], ["ТОО «АйТи Сервис Плюс»", 0.25, "Частично"]];
  bars.forEach(([name, pct, status], i) => {
    const by = ry + 2.8 + i * 0.68;
    s.addText(name, { x: rx + 0.3, y: by, w: rw - 1.3, h: 0.24, fontFace: BODY, fontSize: 9.5, color: INK, margin: 0 });
    s.addText(status, { x: rx + rw - 1.15, y: by, w: 0.9, h: 0.24, fontFace: BODY, fontSize: 8.5, bold: true,
      color: pct === 1.0 ? GREEND : "B45309", margin: 0, align: "right" });
    s.addShape(p.ShapeType.roundRect, { x: rx + 0.3, y: by + 0.27, w: rw - 0.6, h: 0.11, rectRadius: 0.05, fill: { color: "E4E9F0" } });
    s.addShape(p.ShapeType.roundRect, { x: rx + 0.3, y: by + 0.27, w: (rw - 0.6) * pct, h: 0.11, rectRadius: 0.05, fill: { color: GREEN } });
  });
  pageNum(s, 3);
})();

// ============================================================ 4. ПРИЁМ
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Раздел «Приём»", "Как загрузить документ");

  const steps = [
    ["1", "Перетащите файл", "или нажмите — в зону загрузки"],
    ["2", "Заполните карточку", "тип, номер, контрагент, дата, сумма, дело"],
    ["3", "Отправьте", "«Принять в архив» — дальше система работает сама"],
  ];
  const n = steps.length, seg = 6.9 / n, cy = 1.85, d = 0.75;
  steps.forEach(([num, t, sub], i) => {
    const cx = MX + seg * i + seg / 2;
    s.addShape(p.ShapeType.ellipse, { x: cx - d / 2, y: cy, w: d, h: d, fill: { color: GREEN }, shadow: sh() });
    s.addText(num, { x: cx - d / 2, y: cy, w: d, h: d, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 20, bold: true, color: NAVYD, margin: 0 });
    if (i < n - 1) s.addText("→", { x: cx + d / 2, y: cy, w: seg - d, h: d, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 20, bold: true, color: "AEBAC7", margin: 0 });
    s.addText(t, { x: cx - seg / 2 + 0.05, y: cy + 0.95, w: seg - 0.1, h: 0.3, align: "center",
      fontFace: HEAD, fontSize: 12.5, bold: true, color: INK, margin: 0 });
    s.addText(sub, { x: cx - seg / 2 + 0.05, y: cy + 1.28, w: seg - 0.1, h: 0.55, align: "center",
      fontFace: BODY, fontSize: 10, color: MUTED, margin: 0, lineSpacingMultiple: 1.05 });
  });

  s.addText("Дальше — автоматически, статус видно в реальном времени:", { x: MX, y: 4.0, w: 6.9, h: 0.3,
    fontFace: HEAD, fontSize: 12.5, bold: true, color: INK, margin: 0 });
  const pipeline = ["Антивирус", "WORM-хранение", "OCR", "Индексация", "ИИ-опись"];
  const pw = (6.9 - 0.15 * (pipeline.length - 1)) / pipeline.length;
  pipeline.forEach((t, i) => {
    const x = MX + i * (pw + 0.15);
    s.addShape(p.ShapeType.roundRect, { x, y: 4.4, w: pw, h: 0.5, rectRadius: 0.08,
      fill: { color: TINTG }, line: { color: "B8EFD8", width: 1 } });
    s.addText(t, { x, y: 4.4, w: pw, h: 0.5, align: "center", valign: "middle",
      fontFace: BODY, fontSize: 10, bold: true, color: GREEND, margin: 0 });
  });

  card(s, MX, 5.2, 6.9, 1.75, TINTN, 0.1);
  s.addText("💡 Поля заполняются сами", { x: MX + 0.3, y: 5.38, w: 6.3, h: 0.3, fontFace: HEAD,
    fontSize: 12.5, bold: true, color: NAVY, margin: 0 });
  s.addText([
    { text: "Срок хранения ", options: { bold: true } }, { text: "— подставляется по типу документа (перечень 279-НҚ).\n" },
    { text: "Номер приказа/распоряжения/протокола ", options: { bold: true } }, { text: "— присваивается архивом, если поле оставить пустым.\n" },
    { text: "Индекс дела ", options: { bold: true } }, { text: "— из номенклатуры или автоматически по году." },
  ], { x: MX + 0.3, y: 5.72, w: 6.3, h: 1.15, fontFace: BODY, fontSize: 11, color: INK, margin: 0, lineSpacingMultiple: 1.2 });

  // right: mock upload form
  const rx = 7.75, rw = 4.95;
  card(s, rx, 1.85, rw, 5.1, WHITE, 0.14);
  s.addText("ПРИЁМ ДОКУМЕНТА", { x: rx + 0.3, y: 2.05, w: rw - 0.6, h: 0.25, fontFace: HEAD,
    fontSize: 10, bold: true, color: GREEND, charSpacing: 1.5, margin: 0 });
  s.addShape(p.ShapeType.roundRect, { x: rx + 0.3, y: 2.4, w: rw - 0.6, h: 0.75, rectRadius: 0.08,
    fill: { color: "F8FAFC" }, line: { color: "23D292", width: 1.4 } });
  s.addText("⬆  Приказ_о_командировке.pdf", { x: rx + 0.3, y: 2.4, w: rw - 0.6, h: 0.75, align: "center", valign: "middle",
    fontFace: BODY, fontSize: 10.5, color: INK, margin: 0 });
  const fields = [["Тип документа", "Приказ"], ["Номер", "автоматически — П-2026/07"],
    ["Дело", "Д-2026-003 (или из номенклатуры)"], ["Дата документа", "05.07.2026"]];
  fields.forEach(([lbl, val], i) => {
    const fy = 3.35 + i * 0.78;
    s.addText(lbl.toUpperCase(), { x: rx + 0.3, y: fy, w: rw - 0.6, h: 0.22, fontFace: HEAD,
      fontSize: 8.5, bold: true, color: MUTED, charSpacing: 0.5, margin: 0 });
    s.addShape(p.ShapeType.roundRect, { x: rx + 0.3, y: fy + 0.24, w: rw - 0.6, h: 0.38, rectRadius: 0.06,
      fill: { color: "FFFFFF" }, line: { color: "E4E9F0", width: 1 } });
    s.addText(val, { x: rx + 0.42, y: fy + 0.24, w: rw - 0.84, h: 0.38, valign: "middle",
      fontFace: BODY, fontSize: 10, color: val.includes("автомат") ? GREEND : INK,
      italic: val.includes("автомат") || val.includes("или"), margin: 0 });
  });
  pageNum(s, 4);
})();

// ============================================================ 5. ДЕЛА
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Раздел «Дела»", "Группировка документов в дело");
  s.addText("Дело — единица хранения: договор, счёт, акт и платёж по одной сделке живут вместе, с общим сроком хранения и нормативными формами.",
    { x: MX, y: 1.55, w: CW, h: 0.55, fontFace: BODY, fontSize: 14, color: MUTED, margin: 0, lineSpacingMultiple: 1.1 });

  const left = [
    ["Завести дело", "«+ Завести дело» — выберите статью номенклатуры (индекс и срок подставятся) или задайте вручную"],
    ["Привязать документы", "Из карточки документа или при загрузке — выпадающий список «Дело»"],
    ["Закрыть дело", "Кнопка «Закрыть дело» — фиксирует крайние даты по документам"],
    ["Сформировать формы", "PDF/DOCX прямо из карточки дела — см. следующий слайд"],
  ];
  left.forEach(([t, d], i) => {
    const y = 2.3 + i * 1.05;
    s.addShape(p.ShapeType.ellipse, { x: MX, y, w: 0.5, h: 0.5, fill: { color: GREEN } });
    s.addText(String(i + 1), { x: MX, y, w: 0.5, h: 0.5, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 14, bold: true, color: NAVYD, margin: 0 });
    s.addText(t, { x: MX + 0.68, y: y - 0.03, w: 5.6, h: 0.32, fontFace: HEAD, fontSize: 13.5, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: MX + 0.68, y: y + 0.3, w: 5.6, h: 0.6, fontFace: BODY, fontSize: 11, color: MUTED, margin: 0, lineSpacingMultiple: 1.1 });
  });

  const rx = 7.3, rw = 5.4;
  card(s, rx, 2.3, rw, 4.6, NAVY, 0.14);
  s.addText("ДЕЛО 02-11 · ТОМ 1", { x: rx + 0.35, y: 2.55, w: rw - 0.7, h: 0.28, fontFace: HEAD,
    fontSize: 10.5, bold: true, color: GREEN, charSpacing: 1, margin: 0 });
  s.addText("Поставка компьютерного оборудования, 2021", { x: rx + 0.35, y: 2.85, w: rw - 0.7, h: 0.45,
    fontFace: HEAD, fontSize: 15, bold: true, color: WHITE, margin: 0 });
  const docs = ["Договор поставки № ПОСТ-2021/07", "Счёт-фактура № СФ-2021/000712",
    "Акт приёма-передачи № АПП-2021/07", "Платёжное поручение № ПП-2021/318", "Накладная № НАКЛ-2021/44"];
  docs.forEach((t, i) => {
    const y = 3.5 + i * 0.42;
    s.addShape(p.ShapeType.ellipse, { x: rx + 0.35, y: y + 0.06, w: 0.09, h: 0.09, fill: { color: GREEN } });
    s.addText(t, { x: rx + 0.58, y: y - 0.06, w: rw - 0.95, h: 0.3, fontFace: BODY, fontSize: 10.5, color: "DCE4EC", margin: 0 });
  });
  s.addShape(p.ShapeType.roundRect, { x: rx + 0.35, y: 5.8, w: rw - 0.7, h: 0.7, rectRadius: 0.08, fill: { color: NAVYD } });
  s.addText("Срок хранения: 5 лет · хранить до 31.12.2026", { x: rx + 0.35, y: 5.8, w: rw - 0.7, h: 0.7,
    align: "center", valign: "middle", fontFace: BODY, fontSize: 11, color: "C7D2DE", margin: 0 });
  pageNum(s, 5);
})();

// ============================================================ 6. ФОРМЫ
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Формы дела", "Нормативные документы одной кнопкой");
  s.addText("В карточке дела — четыре формы по правилам архивного дела РК (приказ МКС № 235), двуязычные (қаз/рус), в PDF и DOCX.",
    { x: MX, y: 1.55, w: CW, h: 0.45, fontFace: BODY, fontSize: 14, color: MUTED, margin: 0 });

  const forms = [
    ["📋", "Внутренняя опись", "прил. 28", "Перечень документов дела с датами и заголовками"],
    ["📃", "Лист-заверитель", "прил. 31", "Количество листов дела цифрами и прописью"],
    ["💾", "Опись эл. дела", "№ 236", "Файлы, объём в байтах, контрольная характеристика SHA-256"],
    ["📕", "Обложка дела", "—", "Индекс, крайние даты, срок хранения"],
  ];
  const cw = (CW - 0.4 * 3) / 4;
  forms.forEach(([emoji, t, ref, d], i) => {
    const x = MX + i * (cw + 0.4);
    card(s, x, 2.35, cw, 3.5);
    s.addText(emoji, { x: x + 0.25, y: 2.6, w: cw - 0.5, h: 0.7, fontFace: HEAD, fontSize: 30, margin: 0 });
    s.addText(t, { x: x + 0.25, y: 3.35, w: cw - 0.5, h: 0.55, fontFace: HEAD, fontSize: 14.5, bold: true, color: INK, margin: 0 });
    if (ref !== "—") s.addText(ref, { x: x + 0.25, y: 3.85, w: cw - 0.5, h: 0.25, fontFace: MONO, fontSize: 9.5, color: GREEND, margin: 0 });
    s.addText(d, { x: x + 0.25, y: 4.15, w: cw - 0.5, h: 1.3, fontFace: BODY, fontSize: 10.5, color: MUTED, margin: 0, lineSpacingMultiple: 1.15 });
  });

  card(s, MX, 6.1, CW, 0.85, TINTG, 0.1);
  s.addText("«→ в архив» сохраняет сформированный PDF как документ дела под WORM-защитой — форма сама становится частью архива.",
    { x: MX + 0.35, y: 6.1, w: CW - 0.7, h: 0.85, valign: "middle", fontFace: BODY, fontSize: 12.5, color: NAVY, margin: 0 });
  pageNum(s, 6);
})();

// ============================================================ 7. НОМЕНКЛАТУРА
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Раздел «Номенклатура»", "Справочник сроков хранения");
  s.addText("Систематизированный перечень дел организации: каждая статья задаёт индекс, заголовок дела и срок хранения по перечню 279-НҚ. Дела наследуют эти значения при выборе статьи.",
    { x: MX, y: 1.55, w: 6.6, h: 1.0, fontFace: BODY, fontSize: 14, color: MUTED, margin: 0, lineSpacingMultiple: 1.15 });

  const presets = [["5 лет", GREEN], ["10 лет", GREEN], ["75 лет", CORAL], ["Постоянно", NAVY], ["До минования надобности", MUTED]];
  presets.forEach(([t, col], i) => {
    const y = 2.85 + i * 0.62;
    s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 2.5, h: 0.46, rectRadius: 0.23, fill: { color: col } });
    s.addText(t, { x: MX, y, w: 2.5, h: 0.46, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 11.5, bold: true, color: col === GREEN ? NAVYD : WHITE, margin: 0 });
  });
  s.addText("Готовые пресеты сроков — выбрали и не ошиблись в цифрах.", { x: MX + 2.85, y: 3.05, w: 4.0, h: 1.0,
    fontFace: BODY, fontSize: 12, color: MUTED, margin: 0, italic: true, lineSpacingMultiple: 1.2 });

  const rx = 7.3, rw = 5.4;
  card(s, rx, 2.3, rw, 4.5, WHITE, 0.14);
  s.addText("НОМЕНКЛАТУРА ДЕЛ", { x: rx + 0.3, y: 2.5, w: rw - 0.6, h: 0.25, fontFace: HEAD,
    fontSize: 10, bold: true, color: GREEND, charSpacing: 1.5, margin: 0 });
  const rows = [["01-05", "Договоры аренды помещений", "5 лет"], ["02-11", "Поставка оборудования", "5 лет"],
    ["04-58", "Кадровые приказы", "75 лет"], ["05-03", "Распорядительные документы", "Постоянно"]];
  rows.forEach(([idx, t, ret], i) => {
    const y = 2.9 + i * 0.75;
    s.addShape(p.ShapeType.roundRect, { x: rx + 0.3, y, w: 0.75, h: 0.42, rectRadius: 0.06, fill: { color: TINTN } });
    s.addText(idx, { x: rx + 0.3, y, w: 0.75, h: 0.42, align: "center", valign: "middle",
      fontFace: MONO, fontSize: 10.5, bold: true, color: NAVY, margin: 0 });
    s.addText(t, { x: rx + 1.2, y: y + 0.02, w: rw - 2.4, h: 0.38, valign: "middle", fontFace: BODY, fontSize: 11, color: INK, margin: 0 });
    s.addText(ret, { x: rx + rw - 1.35, y: y + 0.02, w: 1.05, h: 0.38, valign: "middle", align: "right",
      fontFace: BODY, fontSize: 10, bold: true, color: GREEND, margin: 0 });
  });
  pageNum(s, 7);
})();

// ============================================================ 8. ИИ-АССИСТЕНТ
(() => {
  const s = p.addSlide();
  s.background = { color: NAVY };
  header(s, "Раздел «ИИ-ассистент»", "Спросите архив обычным языком", true);
  s.addText("Работает локально (данные не покидают периметр). Понимает и содержимое документов, и метаданные — сам выбирает, что искать.",
    { x: MX, y: 1.55, w: CW, h: 0.5, fontFace: BODY, fontSize: 14, color: "C7D2DE", margin: 0 });

  const examples = [
    ["По содержимому", "«Какие условия оплаты в договоре подряда?»", GREEN],
    ["По метаданным", "«Покажи все счета-фактуры за 2021 год»", CORAL],
    ["Агрегаты", "«Сколько мы заплатили ТОО Кагаз Логистик?»", GREEN],
    ["Сроки хранения", "«Какие документы истекают в этом году?»", CORAL],
  ];
  const cw = (CW - 0.4 * 3) / 4;
  examples.forEach(([lbl, ex, col], i) => {
    const x = MX + i * (cw + 0.4);
    s.addShape(p.ShapeType.roundRect, { x, y: 2.5, w: cw, h: 2.6, rectRadius: 0.12, fill: { color: NAVYD } });
    s.addShape(p.ShapeType.roundRect, { x: x + 0.22, y: 2.72, w: cw - 0.44, h: 0.4, rectRadius: 0.2, fill: { color: col } });
    s.addText(lbl, { x: x + 0.22, y: 2.72, w: cw - 0.44, h: 0.4, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 10.5, bold: true, color: NAVYD, margin: 0 });
    s.addText(ex, { x: x + 0.24, y: 3.35, w: cw - 0.48, h: 1.55, fontFace: BODY, fontSize: 12,
      italic: true, color: "E4E9F0", margin: 0, valign: "top", lineSpacingMultiple: 1.2 });
  });

  card(s, MX, 5.5, CW, 1.35, WHITE, 0.12);
  s.addText([
    { text: "Каждый ответ ", options: { color: MUTED } },
    { text: "со ссылкой на документ-источник", options: { bold: true, color: GREEND } },
    { text: " — открывается кликом на источник в самом ответе. Быстрые вопросы (обзор, сроки, суммы) отвечают мгновенно, без ожидания модели.",
      options: { color: MUTED } },
  ], { x: MX + 0.35, y: 5.5, w: CW - 0.7, h: 1.35, valign: "middle", fontFace: BODY, fontSize: 13, margin: 0, lineSpacingMultiple: 1.2 });
  pageNum(s, 8);
})();

// ============================================================ 9. ВЫДАЧА
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Раздел «Выдача»", "Дело во временное пользование");
  s.addText("Заказ → выдача → возврат, с контролем просроченных — по правилам ведомственного архива (прил. 20–22 приказа № 235).",
    { x: MX, y: 1.55, w: CW, h: 0.45, fontFace: BODY, fontSize: 14, color: MUTED, margin: 0 });

  const steps = [
    ["Заказ", "«+ Заказ на выдачу» — дело, кому выдаётся, цель, срок возврата", GREEN],
    ["Выдать", "Кнопка «Выдать» в строке заказа — дело помечено «на руках»", GREEN],
    ["Вернуть", "Кнопка «Вернуть» — фиксирует дату возврата", CORAL],
  ];
  const n = steps.length, seg = CW / n, cy = 2.5, d = 0.7;
  steps.forEach(([t, d2, col], i) => {
    const cx = MX + seg * i + seg / 2;
    s.addShape(p.ShapeType.ellipse, { x: cx - d / 2, y: cy, w: d, h: d, fill: { color: col }, shadow: sh() });
    s.addText(String(i + 1), { x: cx - d / 2, y: cy, w: d, h: d, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 18, bold: true, color: col === CORAL ? WHITE : NAVYD, margin: 0 });
    if (i < n - 1) s.addText("→", { x: cx + d / 2, y: cy, w: seg - d, h: d, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 20, bold: true, color: "AEBAC7", margin: 0 });
    s.addText(t, { x: cx - seg / 2 + 0.2, y: cy + 0.9, w: seg - 0.4, h: 0.32, align: "center",
      fontFace: HEAD, fontSize: 14, bold: true, color: INK, margin: 0 });
    s.addText(d2, { x: cx - seg / 2 + 0.4, y: cy + 1.25, w: seg - 0.8, h: 0.85, align: "center",
      fontFace: BODY, fontSize: 11, color: MUTED, margin: 0, lineSpacingMultiple: 1.1 });
  });

  card(s, MX, 4.95, CW, 1.9, WHITE, 0.12);
  s.addText("КНИГА ВЫДАЧИ ДЕЛ", { x: MX + 0.35, y: 5.15, w: 6, h: 0.25, fontFace: HEAD,
    fontSize: 10, bold: true, color: GREEND, charSpacing: 1.5, margin: 0 });
  const rows = [["02-11", "Смагулова А.Н.", "19.07.2026", "25.07.2026", "Возвращено", "b-green"]];
  rows.forEach(([idx, who, out, due, status], i) => {
    const y = 5.5 + i * 0.4;
    s.addText(idx, { x: MX + 0.35, y, w: 1, h: 0.32, fontFace: MONO, fontSize: 10.5, bold: true, color: NAVY, margin: 0, valign: "middle" });
    s.addText(who, { x: MX + 1.5, y, w: 2.6, h: 0.32, fontFace: BODY, fontSize: 10.5, color: INK, margin: 0, valign: "middle" });
    s.addText(`выдано ${out}`, { x: MX + 4.3, y, w: 2.2, h: 0.32, fontFace: BODY, fontSize: 10, color: MUTED, margin: 0, valign: "middle" });
    s.addText(`возврат до ${due}`, { x: MX + 6.6, y, w: 2.4, h: 0.32, fontFace: BODY, fontSize: 10, color: MUTED, margin: 0, valign: "middle" });
    s.addShape(p.ShapeType.roundRect, { x: MX + CW - 1.7, y, w: 1.4, h: 0.32, rectRadius: 0.16, fill: { color: TINTG } });
    s.addText(status, { x: MX + CW - 1.7, y, w: 1.4, h: 0.32, align: "center", valign: "middle",
      fontFace: BODY, fontSize: 9.5, bold: true, color: GREEND, margin: 0 });
  });
  s.addText("⚠ Просроченные заказы подсвечиваются красным вверху страницы — не пропустите.", { x: MX + 0.35, y: 6.1, w: CW - 0.7, h: 0.4,
    fontFace: BODY, fontSize: 11, italic: true, color: CORAL, margin: 0 });
  pageNum(s, 9);
})();

// ============================================================ 10. УНИЧТОЖЕНИЕ
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Раздел «Уничтожение»", "Экспертиза ценности документов");
  s.addText("Когда срок хранения истёк — раздел подсказывает, что можно списать, и готовит акт по установленной форме.",
    { x: MX, y: 1.55, w: CW, h: 0.45, fontFace: BODY, fontSize: 14, color: MUTED, margin: 0 });

  const steps = [
    ["1", "Отметьте документы", "в списке «Документы с истёкшим сроком хранения» — чекбоксы"],
    ["2", "Сформируйте акт", "«Сформировать акт на уничтожение» — номер и позиции автоматически"],
    ["3", "Утвердите (админ)", "Кнопка «Утвердить акт» — документы помечаются уничтоженными и уходят из поиска"],
  ];
  steps.forEach(([num, t, d], i) => {
    const y = 2.35 + i * 1.05;
    s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 0.55, h: 0.55, rectRadius: 0.1, fill: { color: i === 2 ? CORAL : GREEN } });
    s.addText(num, { x: MX, y, w: 0.55, h: 0.55, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 16, bold: true, color: i === 2 ? WHITE : NAVYD, margin: 0 });
    s.addText(t, { x: MX + 0.75, y: y - 0.02, w: 5.6, h: 0.32, fontFace: HEAD, fontSize: 13.5, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: MX + 0.75, y: y + 0.3, w: 5.6, h: 0.6, fontFace: BODY, fontSize: 11, color: MUTED, margin: 0, lineSpacingMultiple: 1.1 });
  });

  const rx = 7.3, rw = 5.4;
  card(s, rx, 2.3, rw, 4.5, NAVY, 0.14);
  s.addText("АКТ АУ-2026/01", { x: rx + 0.35, y: 2.55, w: rw - 0.7, h: 0.3, fontFace: HEAD,
    fontSize: 13, bold: true, color: WHITE, margin: 0 });
  s.addShape(p.ShapeType.roundRect, { x: rx + rw - 1.75, y: 2.55, w: 1.4, h: 0.34, rectRadius: 0.17, fill: { color: GREEN } });
  s.addText("Утверждён", { x: rx + rw - 1.75, y: 2.55, w: 1.4, h: 0.34, align: "center", valign: "middle",
    fontFace: BODY, fontSize: 9.5, bold: true, color: NAVYD, margin: 0 });
  s.addText("Электронные документы, прил. 15", { x: rx + 0.35, y: 2.95, w: rw - 0.7, h: 0.28,
    fontFace: BODY, fontSize: 10, italic: true, color: "94A3B8", margin: 0 });
  const items = ["Договор аренды офисного помещения — 31.12.2024", "Счёт-фактура за аренду (март 2020) — 31.12.2025",
    "Платёжное поручение за аренду — 31.12.2025"];
  items.forEach((t, i) => {
    const y = 3.5 + i * 0.55;
    s.addShape(p.ShapeType.ellipse, { x: rx + 0.35, y: y + 0.08, w: 0.08, h: 0.08, fill: { color: CORAL } });
    s.addText(t, { x: rx + 0.58, y: y - 0.05, w: rw - 0.95, h: 0.42, fontFace: BODY, fontSize: 10, color: "DCE4EC", margin: 0, lineSpacingMultiple: 1.05 });
  });
  s.addShape(p.ShapeType.line, { x: rx + 0.35, y: 5.3, w: rw - 0.7, h: 0, line: { color: "3A4A5E", width: 1 } });
  s.addText("Итого: 5 документов · книга учёта обновляется автоматически", { x: rx + 0.35, y: 5.45, w: rw - 0.7, h: 0.55,
    fontFace: BODY, fontSize: 10.5, italic: true, color: "94A3B8", margin: 0, lineSpacingMultiple: 1.1 });
  pageNum(s, 10);
})();

// ============================================================ 11. ЭКСПОРТ И ЭЦП
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  header(s, "Экспорт и подпись", "Передача данных вовне архива");

  const cw = (CW - 0.4) / 2;
  // left: export
  card(s, MX, 2.1, cw, 4.6);
  s.addText("📦", { x: MX + 0.3, y: 2.35, w: 0.8, h: 0.6, fontFace: HEAD, fontSize: 26, margin: 0 });
  s.addText("Экспорт дела (ZIP)", { x: MX + 0.3, y: 3.0, w: cw - 0.6, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: INK, margin: 0 });
  s.addText("Кнопка в карточке дела формирует информационный пакет для передачи в госархив:",
    { x: MX + 0.3, y: 3.45, w: cw - 0.6, h: 0.5, fontFace: BODY, fontSize: 12, color: MUTED, margin: 0, lineSpacingMultiple: 1.15 });
  ["Файлы всех документов дела", "manifest.json — метаданные и хэши", "control_sheet.txt — контрольный лист", "opis.pdf — опись электронного дела"]
    .forEach((t, i) => {
      const y = 4.05 + i * 0.42;
      s.addShape(p.ShapeType.ellipse, { x: MX + 0.35, y: y + 0.07, w: 0.09, h: 0.09, fill: { color: GREEN } });
      s.addText(t, { x: MX + 0.58, y, w: cw - 0.95, h: 0.35, fontFace: BODY, fontSize: 11.5, color: INK, margin: 0, valign: "middle" });
    });
  s.addText("Также доступны: акт проверки наличия (сверка с хранилищем) и акт миграции — обе кнопки в разделе «Уничтожение».",
    { x: MX + 0.3, y: 5.85, w: cw - 0.6, h: 0.65, fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED, margin: 0, lineSpacingMultiple: 1.15 });

  // right: ЭЦП
  const rx = MX + cw + 0.4;
  card(s, rx, 2.1, cw, 4.6);
  s.addText("🔏", { x: rx + 0.3, y: 2.35, w: 0.8, h: 0.6, fontFace: HEAD, fontSize: 26, margin: 0 });
  s.addText("Подпись и заверенная копия", { x: rx + 0.3, y: 3.0, w: cw - 0.6, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: INK, margin: 0 });
  s.addText("Из карточки документа:", { x: rx + 0.3, y: 3.45, w: cw - 0.6, h: 0.3, fontFace: BODY, fontSize: 12, color: MUTED, margin: 0 });
  const ecp = [["🔏 Подписать и проверить ЭЦП", "вызывает NCALayer, проверяет подпись (НУЦ РК)"],
    ["📄 Заверенная копия", "PDF с результатом проверки ЭЦП и штампом «Копия верна»"]];
  ecp.forEach(([t, d], i) => {
    const y = 3.9 + i * 0.95;
    s.addShape(p.ShapeType.roundRect, { x: rx + 0.3, y, w: cw - 0.6, h: 0.4, rectRadius: 0.08, fill: { color: TINTN } });
    s.addText(t, { x: rx + 0.45, y, w: cw - 0.9, h: 0.4, valign: "middle", fontFace: BODY, fontSize: 11.5, bold: true, color: NAVY, margin: 0 });
    s.addText(d, { x: rx + 0.3, y: y + 0.45, w: cw - 0.6, h: 0.4, fontFace: BODY, fontSize: 10.5, color: MUTED, margin: 0, lineSpacingMultiple: 1.1 });
  });
  s.addText("Требуется установленный NCALayer на компьютере сотрудника.", { x: rx + 0.3, y: 5.85, w: cw - 0.6, h: 0.5,
    fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED, margin: 0 });
  pageNum(s, 11);
})();

// ============================================================ 12. ШПАРГАЛКА
(() => {
  const s = p.addSlide();
  s.background = { color: NAVY };
  kicker(s, "Шпаргалка", MX, 0.55, GREEN);
  title(s, "Частые задачи — куда идти", MX, 0.9, WHITE);

  const tasks = [
    ["Загрузить новый документ", "Приём"],
    ["Найти документ по смыслу или спросить сумму", "ИИ-ассистент"],
    ["Собрать договор+счёт+акт в одно дело", "Дела"],
    ["Узнать, что можно списать", "Уничтожение"],
    ["Выдать дело сотруднику на время", "Выдача"],
    ["Проверить общую картину по деньгам", "Дашборд"],
    ["Задать срок хранения для нового вида дел", "Номенклатура"],
    ["Скачать опись или лист-заверитель", "Дела → форма"],
  ];
  const cols = 2, gap = 0.5, cw = (CW - gap) / cols, ch = 0.85;
  tasks.forEach(([task, dest], i) => {
    const r = Math.floor(i / cols), c = i % cols;
    const x = MX + c * (cw + gap), y = 2.05 + r * (ch + 0.22);
    s.addShape(p.ShapeType.roundRect, { x, y, w: cw, h: ch, rectRadius: 0.1, fill: { color: NAVYD } });
    s.addText(task, { x: x + 0.25, y: y + 0.1, w: cw - 2.1, h: ch - 0.2, valign: "middle",
      fontFace: BODY, fontSize: 11.5, color: "E4E9F0", margin: 0, lineSpacingMultiple: 1.05 });
    s.addShape(p.ShapeType.roundRect, { x: x + cw - 1.85, y: y + ch / 2 - 0.19, w: 1.65, h: 0.38, rectRadius: 0.19, fill: { color: GREEN } });
    s.addText(dest, { x: x + cw - 1.85, y: y + ch / 2 - 0.19, w: 1.65, h: 0.38, align: "center", valign: "middle",
      fontFace: HEAD, fontSize: 9.5, bold: true, color: NAVYD, margin: 0 });
  });

  s.addText("Вопросы — к администратору архива или в раздел «ИИ-ассистент» (он тоже знает, как устроен архив).",
    { x: MX, y: 6.75, w: CW, h: 0.4, fontFace: BODY, fontSize: 12, italic: true, color: "8A98A8", margin: 0, align: "center" });
})();

p.writeFile({ fileName: "C:/Users/Жанболат/Documents/e-archive/presentation/e-archive-user-guide.pptx" })
  .then((f) => console.log("WROTE", f));
