const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
p.author = "e-archive";
p.title = "e-archive — Инвестиционная презентация";

// ---------- palette ----------
const NAVY = "202D3D", NAVYD = "13262F", GREEN = "23D292", GREEND = "18A872",
      CORAL = "FF8562", LIGHT = "F0F4F9", INK = "202D3D", WHITE = "FFFFFF",
      MUTED = "5C6672", TINTG = "E7F8F0", TINTC = "FDEEE8", TINTN = "E9EEF4";
const HEAD = "Calibri", BODY = "Calibri";
const W = 13.33, H = 7.5, MX = 0.62, CW = W - MX * 2;

const sh = (o = {}) => Object.assign({ type: "outer", color: "202D3D", opacity: 0.18, blur: 10, offset: 3, angle: 90 }, o);

function kicker(s, txt, x, y, col = GREEN) {
  s.addText(txt.toUpperCase(), { x, y, w: 6, h: 0.3, fontFace: HEAD, fontSize: 12,
    bold: true, color: col, charSpacing: 2, margin: 0 });
}
function title(s, txt, x, y, col = INK, w = CW, size = 38) {
  s.addText(txt, { x, y, w, h: 0.9, fontFace: HEAD, fontSize: size, bold: true,
    color: col, margin: 0 });
}
function circle(s, x, y, d, fill, label, lc = WHITE, fs = 15) {
  s.addShape(p.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: fill }, shadow: sh() });
  s.addText(label, { x, y, w: d, h: d, align: "center", valign: "middle",
    fontFace: HEAD, fontSize: fs, bold: true, color: lc, margin: 0 });
}
function card(s, x, y, w, h, fill = WHITE, radius = 0.12) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: radius,
    fill: { color: fill }, line: { color: "E4E9F0", width: 1 }, shadow: sh() });
}

// ============================================================ 1. COVER
(() => {
  const s = p.addSlide();
  s.background = { color: NAVY };
  // subtle geometric motif — concentric rings, top-right
  [3.4, 2.5, 1.6].forEach((d, i) =>
    s.addShape(p.ShapeType.ellipse, { x: 10.7 - d / 2, y: 1.2 - d / 2, w: d, h: d,
      fill: { type: "none" }, line: { color: i === 1 ? GREEN : "34465A", width: i === 1 ? 2.5 : 1 } }));
  s.addShape(p.ShapeType.roundRect, { x: MX, y: 1.05, w: 0.9, h: 0.9, rectRadius: 0.16,
    fill: { color: GREEN } });
  s.addText("e", { x: MX, y: 1.05, w: 0.9, h: 0.9, align: "center", valign: "middle",
    fontFace: HEAD, fontSize: 46, bold: true, color: NAVYD, margin: 0 });
  s.addText("e-archive", { x: 1.65, y: 1.15, w: 8, h: 0.75, fontFace: HEAD, fontSize: 34,
    bold: true, color: WHITE, margin: 0, valign: "middle" });

  s.addText("Электронный архив нового поколения", { x: MX, y: 2.9, w: 11.5, h: 0.9,
    fontFace: HEAD, fontSize: 44, bold: true, color: WHITE, margin: 0 });
  s.addText([
    { text: "ИИ-агент · OCR · ЭЦП РК · нормативные формы · ", options: { color: "C7D2DE" } },
    { text: "100% open-source", options: { color: GREEN, bold: true } },
  ], { x: MX, y: 3.95, w: 11.5, h: 0.5, fontFace: BODY, fontSize: 19, margin: 0 });

  s.addText("Инвестиционная презентация · 2026", { x: MX, y: 6.5, w: 8, h: 0.4,
    fontFace: HEAD, fontSize: 14, bold: true, color: "8A98A8", charSpacing: 1, margin: 0 });
  s.addText("Цифровой суверенитет · импортозамещение архивных технологий РК",
    { x: 5.2, y: 6.5, w: 7.5, h: 0.4, fontFace: BODY, fontSize: 13, color: "8A98A8",
      align: "right", margin: 0 });
  s.addNotes("e-archive — рабочий MVP электронного архива с ИИ. Инвестиционная презентация, 11 слайдов: проблема, продукт, конвейер приёма, ИИ-агент, технологии, рынок, нормативное соответствие РК, бизнес-модель.");
})();

// ============================================================ 2. PROBLEM
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Проблема", MX, 0.55, CORAL);
  title(s, "Архивы всё ещё живут на бумаге", MX, 0.9);

  const stats = [
    ["часы–дни", "уходят на поиск нужного документа в бумажном архиве", CORAL],
    ["вручную", "опись, лист-заверитель и акты архивариус заполняет руками", NAVY],
    ["риск", "утраты, порчи и подделки бумажных оригиналов", CORAL],
    ["импорт", "зависимость от иностранного проприетарного ПО", NAVY],
  ];
  const cw = (CW - 0.4 * 3) / 4;
  stats.forEach(([big, txt, col], i) => {
    const x = MX + i * (cw + 0.4);
    card(s, x, 2.35, cw, 3.3);
    s.addText(big, { x: x + 0.25, y: 2.75, w: cw - 0.5, h: 0.9, fontFace: HEAD,
      fontSize: 34, bold: true, color: col, margin: 0 });
    s.addText(txt, { x: x + 0.25, y: 3.75, w: cw - 0.5, h: 1.7, fontFace: BODY,
      fontSize: 15, color: INK, margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  });
  s.addText("Оцифровка идёт медленно, а существующие решения — тяжёлые, закрытые и не заточены под казахстанскую ЭЦП и требования к суверенности данных.",
    { x: MX, y: 6.05, w: CW, h: 0.7, fontFace: BODY, fontSize: 15, italic: true,
      color: MUTED, margin: 0 });
})();

// ============================================================ 3. SOLUTION
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Решение", MX, 0.55);
  title(s, "e-archive — умный электронный архив", MX, 0.9);
  s.addText("Загружаете документ — система сама проверяет, надёжно хранит, распознаёт текст и делает его мгновенно находимым. Вопросы задаёте обычным языком — отвечает ИИ-агент.",
    { x: MX, y: 1.95, w: 7.0, h: 1.4, fontFace: BODY, fontSize: 17, color: INK,
      margin: 0, lineSpacingMultiple: 1.15 });

  const pil = [
    ["Надёжное хранение", "WORM-неизменяемость, контроль целостности, антивирус на приёме"],
    ["ИИ-поиск", "Семантический поиск по смыслу и метаданным, а не по точным словам"],
    ["Юридическая значимость", "Подписание и проверка казахстанской ЭЦП (НУЦ РК)"],
  ];
  pil.forEach(([t, d], i) => {
    const y = 3.55 + i * 1.02;
    circle(s, MX, y, 0.62, GREEN, String(i + 1), NAVYD, 18);
    s.addText(t, { x: MX + 0.85, y: y - 0.06, w: 6.2, h: 0.4, fontFace: HEAD,
      fontSize: 17, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: MX + 0.85, y: y + 0.34, w: 6.3, h: 0.6, fontFace: BODY,
      fontSize: 13.5, color: MUTED, margin: 0 });
  });

  // right visual: stacked "document -> AI" panel
  const rx = 8.1, rw = 4.6;
  card(s, rx, 1.95, rw, 4.65, NAVY, 0.14);
  s.addText("ЧТО ВНУТРИ", { x: rx + 0.4, y: 2.25, w: rw - 0.8, h: 0.3, fontFace: HEAD,
    fontSize: 12, bold: true, color: GREEN, charSpacing: 2, margin: 0 });
  const feats = ["Приём, дела и номенклатура", "OCR: рус · каз · eng",
    "Семантический индекс (векторный)", "Диалоговый ИИ-агент",
    "Нормативные формы РК (PDF/DOCX)", "ЭЦП, роли, веб-приложение (PWA)"];
  feats.forEach((f, i) => {
    const y = 2.75 + i * 0.6;
    s.addShape(p.ShapeType.ellipse, { x: rx + 0.42, y: y + 0.06, w: 0.14, h: 0.14, fill: { color: GREEN } });
    s.addText(f, { x: rx + 0.72, y: y - 0.05, w: rw - 1.1, h: 0.4, fontFace: BODY,
      fontSize: 14.5, color: WHITE, margin: 0, valign: "middle" });
  });
})();

// ============================================================ 4. PROCESS
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Как это работает", MX, 0.55);
  title(s, "Конвейер приёма документа", MX, 0.9);

  const steps = [
    ["1", "Приём", "загрузка файла или скана"],
    ["2", "Антивирус", "проверка ClamAV на приёме"],
    ["3", "WORM-хранение", "неизменяемый оригинал (Object Lock)"],
    ["4", "OCR", "распознавание текста рус/каз/eng"],
    ["5", "Индексация", "векторы + метаданные для поиска"],
    ["6", "Авто-опись", "ИИ сам составляет аннотацию"],
  ];
  const n = steps.length, seg = CW / n, d = 1.0, cy = 2.9;
  steps.forEach(([num, t, sub], i) => {
    const cx = MX + seg * i + seg / 2;
    const fill = i === n - 1 ? CORAL : GREEN;
    circle(s, cx - d / 2, cy, d, fill, num, i === n - 1 ? WHITE : NAVYD, 22);
    if (i < n - 1)
      s.addText("→", { x: cx + d / 2, y: cy, w: seg - d, h: d, align: "center",
        valign: "middle", fontFace: HEAD, fontSize: 24, bold: true, color: "AEBAC7", margin: 0 });
    s.addText(t, { x: cx - seg / 2 + 0.1, y: cy + 1.15, w: seg - 0.2, h: 0.4, align: "center",
      fontFace: HEAD, fontSize: 15, bold: true, color: INK, margin: 0 });
    s.addText(sub, { x: cx - seg / 2 + 0.1, y: cy + 1.55, w: seg - 0.2, h: 0.8, align: "center",
      fontFace: BODY, fontSize: 12, color: MUTED, margin: 0 });
  });

  card(s, MX, 5.55, CW, 1.15, TINTG, 0.1);
  s.addText([
    { text: "Асинхронно и прозрачно.  ", options: { bold: true, color: GREEND } },
    { text: "Статус документа обновляется в реальном времени: Антивирус → Обработка → Готов. Каждый шаг фиксируется, оригинал остаётся под WORM-защитой навсегда.",
      options: { color: INK } },
  ], { x: MX + 0.35, y: 5.7, w: CW - 0.7, h: 0.85, fontFace: BODY, fontSize: 14.5,
    valign: "middle", margin: 0, lineSpacingMultiple: 1.1 });
})();

// ============================================================ 5. AI ASSISTANT
(() => {
  const s = p.addSlide();
  s.background = { color: NAVY };
  kicker(s, "Ключевая инновация", MX, 0.55, GREEN);
  title(s, "ИИ-агент, который читает ваши документы", MX, 0.9, WHITE);
  s.addText("Диалоговый помощник ищет и по СОДЕРЖИМОМУ документов, и по МЕТАДАННЫМ — сам решает, каким инструментом воспользоваться, и отвечает со ссылками на источники.",
    { x: MX, y: 1.9, w: 5.55, h: 1.7, fontFace: BODY, fontSize: 16, color: "C7D2DE",
      margin: 0, lineSpacingMultiple: 1.15 });

  const tools = [
    ["search_archive", "поиск по смыслу содержимого"],
    ["filter_documents", "выборка по типу, дате, сумме, контрагенту"],
    ["read_document", "чтение полного текста документа"],
  ];
  tools.forEach(([t, d], i) => {
    const y = 3.75 + i * 0.92;
    s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 2.35, h: 0.55, rectRadius: 0.08,
      fill: { color: NAVYD }, line: { color: GREEN, width: 1 } });
    s.addText(t, { x: MX, y, w: 2.35, h: 0.55, align: "center", valign: "middle",
      fontFace: "Consolas", fontSize: 12.5, bold: true, color: GREEN, margin: 0 });
    s.addText(d, { x: MX + 2.55, y, w: 3.0, h: 0.55, fontFace: BODY, fontSize: 13,
      color: "C7D2DE", valign: "middle", margin: 0 });
  });

  // mock chat card on the right
  const rx = 6.5, rw = 6.2;
  card(s, rx, 1.9, rw, 4.9, WHITE, 0.14);
  s.addText("«Покажи все счета-фактуры за 2021 год и на какую сумму»",
    { x: rx + 0.35, y: 2.2, w: rw - 0.7, h: 0.55, fontFace: BODY, fontSize: 14,
      italic: true, color: INK, margin: 0, fill: { color: TINTN }, align: "left", valign: "middle" });
  s.addText("ДЕЙСТВИЯ АГЕНТА", { x: rx + 0.35, y: 2.95, w: rw - 0.7, h: 0.3, fontFace: HEAD,
    fontSize: 10.5, bold: true, color: GREEND, charSpacing: 1.5, margin: 0 });
  s.addText("filter_documents(doc_type=Счёт-фактура, year=2021)",
    { x: rx + 0.35, y: 3.25, w: rw - 0.7, h: 0.4, fontFace: "Consolas", fontSize: 11.5,
      color: MUTED, margin: 0, valign: "middle" });
  s.addShape(p.ShapeType.line, { x: rx + 0.35, y: 3.75, w: rw - 0.7, h: 0, line: { color: "E4E9F0", width: 1 } });
  s.addText([
    { text: "В 2021 году выдана 1 счёт-фактура на сумму ", options: { color: INK } },
    { text: "12 800 000 ₸", options: { color: GREEND, bold: true } },
    { text: " контрагенту ТОО «Кагаз Логистик» (№ СФ-2021/000712).", options: { color: INK } },
  ], { x: rx + 0.35, y: 3.9, w: rw - 0.7, h: 1.4, fontFace: BODY, fontSize: 15,
    margin: 0, valign: "top", lineSpacingMultiple: 1.15 });
  s.addShape(p.ShapeType.roundRect, { x: rx + 0.35, y: 5.9, w: rw - 0.7, h: 0.6, rectRadius: 0.08,
    fill: { color: TINTG } });
  s.addText("Источник: Счёт-фактура на серверное оборудование (СФ-2021/000712)",
    { x: rx + 0.55, y: 5.9, w: rw - 1.0, h: 0.6, fontFace: BODY, fontSize: 12,
      color: GREEND, bold: true, valign: "middle", margin: 0 });
})();

// ============================================================ 6. APPLIED TECH
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Применённые технологии", MX, 0.55);
  title(s, "Инновации, уже работающие в MVP", MX, 0.9);

  const items = [
    ["LLM", "Локальный ИИ-агент", "qwen2.5:7b на GPU — данные не покидают периметр", GREEN],
    ["RAG", "Семантический поиск", "Векторные эмбеддинги + гибрид с полнотекстом", GREEN],
    ["OCR", "Распознавание текста", "Tesseract (rus/kaz/eng); опционально Unlimited-OCR (VLM) на GPU", NAVY],
    ["ЭЦП", "Казахстанская подпись", "Интеграция NCALayer, проверка CMS (НУЦ РК)", NAVY],
    ["WORM", "Неизменяемое хранение", "MinIO Object Lock — защита оригиналов", CORAL],
    ["OSS", "Open-source стек", "PostgreSQL · OpenSearch · MinIO · Docker", CORAL],
  ];
  const cols = 3, gap = 0.4, cw = (CW - gap * (cols - 1)) / cols, ch = 1.95;
  items.forEach((it, i) => {
    const r = Math.floor(i / cols), c = i % cols;
    const x = MX + c * (cw + gap), y = 2.3 + r * (ch + 0.35);
    card(s, x, y, cw, ch);
    circle(s, x + 0.3, y + 0.32, 0.74, it[3], it[0], it[3] === CORAL ? WHITE : NAVYD, 13);
    s.addText(it[1], { x: x + 1.2, y: y + 0.32, w: cw - 1.45, h: 0.5, fontFace: HEAD,
      fontSize: 16, bold: true, color: INK, margin: 0, valign: "middle" });
    s.addText(it[2], { x: x + 0.3, y: y + 1.15, w: cw - 0.55, h: 0.7, fontFace: BODY,
      fontSize: 13, color: MUTED, margin: 0, lineSpacingMultiple: 1.05 });
  });
})();

// ============================================================ 7. SOVEREIGNTY
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Технологический суверенитет", MX, 0.55, CORAL);
  title(s, "Импортозамещение по умолчанию", MX, 0.9);

  const stats = [["100%", "open-source компоненты"], ["0", "данных уходит наружу"],
    ["3", "языка OCR: рус/каз/eng"], ["РК", "ЭЦП НУЦ, соответствие требованиям"]];
  const cw = (CW - 0.4 * 3) / 4;
  stats.forEach(([b, t], i) => {
    const x = MX + i * (cw + 0.4);
    card(s, x, 2.3, cw, 1.75);
    s.addText(b, { x: x + 0.2, y: 2.5, w: cw - 0.4, h: 0.75, fontFace: HEAD, fontSize: 38,
      bold: true, color: GREEND, margin: 0, align: "center" });
    s.addText(t, { x: x + 0.2, y: 3.3, w: cw - 0.4, h: 0.6, fontFace: BODY, fontSize: 13,
      color: INK, margin: 0, align: "center", lineSpacingMultiple: 1.05 });
  });

  card(s, MX, 4.4, CW, 2.25, NAVY, 0.14);
  s.addText("Почему это важно инвестору", { x: MX + 0.45, y: 4.65, w: 11, h: 0.45,
    fontFace: HEAD, fontSize: 18, bold: true, color: GREEN, margin: 0 });
  const pts = [
    "Локальная модель ИИ — конфиденциальные документы не отправляются во внешние облака.",
    "Отсутствие лицензионной зависимости от зарубежных вендоров и санкционных рисков.",
    "Соответствие тренду на цифровой суверенитет и требованиям госсектора РК.",
  ];
  pts.forEach((t, i) => {
    const y = 5.2 + i * 0.45;
    s.addShape(p.ShapeType.ellipse, { x: MX + 0.5, y: y + 0.08, w: 0.13, h: 0.13, fill: { color: GREEN } });
    s.addText(t, { x: MX + 0.8, y, w: CW - 1.2, h: 0.4, fontFace: BODY, fontSize: 14,
      color: WHITE, valign: "middle", margin: 0 });
  });
})();

// ============================================================ 8. MARKET
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Рынок", MX, 0.55);
  title(s, "Кому это нужно", MX, 0.9);

  const segs = [
    ["Госсектор и архивы", "Госорганы, акиматы, национальные архивы — обязательная оцифровка и долгосрочное хранение.", NAVY],
    ["Крупный бизнес", "Банки, недропользователи, логистика — миллионы договоров, счетов и актов.", GREEN],
    ["МСБ и услуги", "Бухгалтерия, кадры, юр-практики — недорогой архив с ИИ-поиском.", CORAL],
  ];
  const cw = (CW - 0.5 * 2) / 3;
  segs.forEach(([t, d, col], i) => {
    const x = MX + i * (cw + 0.5);
    card(s, x, 2.3, cw, 2.5);
    s.addShape(p.ShapeType.roundRect, { x: x + 0.3, y: 2.6, w: 0.55, h: 0.55, rectRadius: 0.1, fill: { color: col } });
    s.addText(t, { x: x + 0.3, y: 3.35, w: cw - 0.6, h: 0.5, fontFace: HEAD, fontSize: 17,
      bold: true, color: INK, margin: 0 });
    s.addText(d, { x: x + 0.3, y: 3.85, w: cw - 0.6, h: 0.85, fontFace: BODY, fontSize: 13,
      color: MUTED, margin: 0, lineSpacingMultiple: 1.1 });
  });

  card(s, MX, 5.15, CW, 1.5, TINTN, 0.1);
  s.addText([
    { text: "Драйверы спроса:  ", options: { bold: true, color: NAVY } },
    { text: "госпрограммы цифровизации · переход на ЭДО · требования к хранению и ЭЦП · импортозамещение ПО. Единый рынок для одного продукта — от национального архива до малого бизнеса.",
      options: { color: INK } },
  ], { x: MX + 0.4, y: 5.3, w: CW - 0.8, h: 1.2, fontFace: BODY, fontSize: 15,
    valign: "middle", margin: 0, lineSpacingMultiple: 1.15 });
})();

// ============================================================ 9. COMPLIANCE (РК)
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Нормативное соответствие РК", MX, 0.55, CORAL);
  title(s, "Формы, которых требует закон — из коробки", MX, 0.9);

  // левая панель: нормативная база
  const lw = 5.3;
  card(s, MX, 1.95, lw, 4.35, NAVY, 0.14);
  s.addText("НОРМАТИВНАЯ БАЗА", { x: MX + 0.4, y: 2.2, w: lw - 0.8, h: 0.3, fontFace: HEAD,
    fontSize: 11.5, bold: true, color: GREEN, charSpacing: 2, margin: 0 });
  const laws = [
    ["Приказ МКС РК № 235", "приём, хранение и учёт документов НАФ"],
    ["Приказ МКС РК № 236", "документирование, ЭРКК, номенклатура дел"],
    ["Перечень 279-НҚ (2025)", "типовые сроки хранения документов"],
    ["Закон № 310-III", "регистрация прав на недвижимое имущество"],
  ];
  laws.forEach(([t, d], i) => {
    const y = 2.65 + i * 0.9;
    s.addText(t, { x: MX + 0.4, y, w: lw - 0.8, h: 0.32, fontFace: HEAD, fontSize: 14.5,
      bold: true, color: WHITE, margin: 0 });
    s.addText(d, { x: MX + 0.4, y: y + 0.33, w: lw - 0.8, h: 0.5, fontFace: BODY,
      fontSize: 12.5, color: "9FB0C2", margin: 0, lineSpacingMultiple: 1.05 });
  });

  // правая панель: что система формирует сама
  const rx = MX + lw + 0.45, rw = W - rx - MX;
  card(s, rx, 1.95, rw, 4.35);
  s.addText("СИСТЕМА ФОРМИРУЕТ АВТОМАТИЧЕСКИ", { x: rx + 0.4, y: 2.2, w: rw - 0.8, h: 0.3,
    fontFace: HEAD, fontSize: 11.5, bold: true, color: GREEND, charSpacing: 1.5, margin: 0 });
  const forms = [
    ["Внутренняя опись дела", "прил. 28"],
    ["Лист-заверитель дела", "прил. 31"],
    ["Опись электронного дела", "№ 236"],
    ["Акт о выделении к уничтожению", "прил. 14/15"],
    ["Заказ и акт выдачи дела", "прил. 20–22"],
    ["Проверка наличия · миграция", "прил. 25/26 · 1"],
  ];
  forms.forEach(([t, tag], i) => {
    const y = 2.68 + i * 0.6;
    s.addShape(p.ShapeType.ellipse, { x: rx + 0.42, y: y + 0.13, w: 0.2, h: 0.2, fill: { color: GREEN } });
    s.addText(t, { x: rx + 0.75, y, w: rw - 2.55, h: 0.45, fontFace: BODY, fontSize: 13,
      color: INK, valign: "middle", margin: 0 });
    s.addText(tag, { x: rx + rw - 1.75, y, w: 1.35, h: 0.45, fontFace: HEAD, fontSize: 11.5,
      bold: true, color: CORAL, align: "right", valign: "middle", margin: 0 });
  });

  card(s, MX, 6.4, CW, 0.6, TINTG, 0.1);
  s.addText([
    { text: "Каждая форма — в PDF и DOCX из данных архива.  ", options: { bold: true, color: GREEND } },
    { text: "33 типа документов · автоматический расчёт сроков хранения · ЭРКК на каждый документ.", options: { color: INK } },
  ], { x: MX + 0.35, y: 6.4, w: CW - 0.7, h: 0.6, fontFace: BODY, fontSize: 13.5,
    valign: "middle", margin: 0 });
  s.addNotes("Нормативное соответствие — обязательное требование госсектора РК и барьер входа для конкурентов. Формы прил. 28 и 31 генерируются из данных архива: архивариусу не нужно заполнять их вручную.");
})();

// ============================================================ 10. BUSINESS MODEL
(() => {
  const s = p.addSlide();
  s.background = { color: LIGHT };
  kicker(s, "Бизнес-модель", MX, 0.55);
  title(s, "Как проект зарабатывает", MX, 0.9);

  const tiers = [
    ["Basic", "Старт / МСБ", ["Электронный архив", "ИИ-поиск и агент", "До 2 пользователей"], NAVY, false],
    ["Standard", "Средний бизнес", ["Всё из Basic", "ЭЦП НУЦ РК", "Дела и номенклатура", "Нормативные формы"], GREEN, true],
    ["Enterprise", "Госсектор / крупные", ["On-premise / суверенно", "SLA и поддержка", "Акты, выдача, PDF/A"], CORAL, false],
  ];
  const cw = (CW - 0.5 * 2) / 3;
  tiers.forEach(([t, seg, feats, col, hot], i) => {
    const x = MX + i * (cw + 0.5), y = hot ? 2.05 : 2.35, hh = hot ? 4.15 : 3.85;
    card(s, x, y, cw, hh, hot ? NAVY : WHITE, 0.14);
    if (hot) s.addText("ПОПУЛЯРНЫЙ", { x: x, y: y + 0.25, w: cw, h: 0.3, align: "center",
      fontFace: HEAD, fontSize: 11, bold: true, color: GREEN, charSpacing: 2, margin: 0 });
    const tc = hot ? WHITE : INK;
    s.addText(t, { x: x + 0.3, y: y + (hot ? 0.65 : 0.35), w: cw - 0.6, h: 0.5, fontFace: HEAD,
      fontSize: 24, bold: true, color: tc, margin: 0, align: "center" });
    s.addText(seg, { x: x + 0.3, y: y + (hot ? 1.2 : 0.9), w: cw - 0.6, h: 0.35, fontFace: BODY,
      fontSize: 13, color: hot ? "C7D2DE" : MUTED, margin: 0, align: "center" });
    feats.forEach((f, j) => {
      const fy = y + (hot ? 1.75 : 1.45) + j * 0.5;
      s.addShape(p.ShapeType.ellipse, { x: x + 0.4, y: fy + 0.08, w: 0.13, h: 0.13, fill: { color: col } });
      s.addText(f, { x: x + 0.65, y: fy, w: cw - 0.95, h: 0.4, fontFace: BODY, fontSize: 13.5,
        color: tc, valign: "middle", margin: 0 });
    });
  });
  s.addText("Регулярный доход по подписке на организацию + внедрение, миграция бумажного архива и обучение персонала.",
    { x: MX, y: 6.55, w: CW, h: 0.4, fontFace: BODY, fontSize: 13.5, italic: true,
      color: MUTED, align: "center", margin: 0 });
})();

// ============================================================ 11. CLOSING
(() => {
  const s = p.addSlide();
  s.background = { color: NAVY };
  [3.6, 2.6, 1.6].forEach((d, i) =>
    s.addShape(p.ShapeType.ellipse, { x: 11.2 - d / 2, y: 6.0 - d / 2, w: d, h: d,
      fill: { type: "none" }, line: { color: i === 1 ? CORAL : "34465A", width: i === 1 ? 2.5 : 1 } }));
  kicker(s, "Инвестиционное предложение", MX, 1.15, GREEN);
  s.addText("Инвестируйте в цифровой\nсуверенитет архивов", { x: MX, y: 1.6, w: 10.5, h: 1.8,
    fontFace: HEAD, fontSize: 40, bold: true, color: WHITE, margin: 0, lineSpacingMultiple: 1.05 });

  const asks = [
    ["Рабочий MVP", "продукт уже запускается и демонстрируется"],
    ["Готовый стек", "open-source, ИИ на GPU, воспроизводимо в 1 команду"],
    ["Большой рынок", "госсектор, бизнес и МСБ в РК и регионе"],
  ];
  const cw = (10.8 - 0.4 * 2) / 3;
  asks.forEach(([t, d], i) => {
    const x = MX + i * (cw + 0.4);
    s.addText(t, { x, y: 4.0, w: cw, h: 0.5, fontFace: HEAD, fontSize: 18, bold: true,
      color: GREEN, margin: 0 });
    s.addText(d, { x, y: 4.5, w: cw, h: 0.9, fontFace: BODY, fontSize: 14, color: "C7D2DE",
      margin: 0, lineSpacingMultiple: 1.1 });
  });

  s.addShape(p.ShapeType.roundRect, { x: MX, y: 6.1, w: 3.5, h: 0.7, rectRadius: 0.1, fill: { color: GREEN } });
  s.addText("Обсудить инвестиции", { x: MX, y: 6.1, w: 3.5, h: 0.7, align: "center",
    valign: "middle", fontFace: HEAD, fontSize: 16, bold: true, color: NAVYD, margin: 0 });
  s.addText("e-archive · zhanbolatkurmanbekuly@gmail.com", { x: 4.4, y: 6.1, w: 8.3, h: 0.7,
    align: "left", valign: "middle", fontFace: BODY, fontSize: 14, color: "8A98A8", margin: 0 });
})();

p.writeFile({ fileName: "C:/Users/Жанболат/Documents/e-archive/presentation/e-archive-investor-deck.pptx" })
  .then((f) => console.log("WROTE", f));
