// Генерує tests/fixtures/site_presets.json: результати СПРАВЖНЬОГО checkRot із site/template.html
// на 6 пресетах сайту. Код сайту виконується без змін; d3 замінено мінімальним мок-об'єктом,
// що зберігає 8 <select> і перехоплює .html() для #ret і #shares.
// Запуск: node tests/gen_site_presets.js
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "site", "template.html"), "utf8");
const a = html.indexOf("// ---------- норматив №164");
const b = html.indexOf("// ---------- метрики", a);
if (a < 0 || b < 0) throw new Error("не знайшов блок №164 у template.html");
const code = html.slice(a, b);

const sels = Array.from({ length: 8 }, () => ({ value: "" }));
const out = {};
function chain(id) {
  const self = new Proxy(function () {}, {
    get(_, k) {
      if (k === "selectAll") return q => (q === "select" ? { each: f => { sels.forEach((s, i) => f.call(s, null, i)); return self; } } : chain(null));
      if (k === "html") return s => { if (id) out[id] = s; return self; };
      return () => self;
    },
    apply() { return self; },
  });
  return self;
}
const d3 = { select: q => chain(q), selectAll: () => chain(null) };

const run = new Function("d3", code + "\nreturn {PRESETS, setRot};");
const { PRESETS, setRot } = run(d3);

const strip = s => s.replace(/<[^>]+>/g, "");
function parseRet(h) {
  const rows = [];
  const re = /<tr><td>(.*?)<\/td><td[^>]*>(.*?)<\/td><td>(.*?)<\/td><td class="(\w*)">(.*?)<\/td><\/tr>/g;
  let m;
  const st = { "✓ так": "ok", "✕ порушення": "bad", "—": "na" };
  while ((m = re.exec(h))) rows.push([m[1], m[2], m[3], st[m[5]]]);
  return rows;
}
function parseShares(h) {
  const res = [];
  const re = /<div class="check"><b class="(\w*)">.*?<\/b><span>(.*?): <b>(\d+)%<\/b> · норма (\d+)–(\d+)%(.*?)<\/span><\/div>/g;
  let m;
  while ((m = re.exec(h))) res.push({ name: m[2], value: +m[3], lo: +m[4], hi: +m[5], status: m[1] === "" ? "na" : m[1], suffix: strip(m[6]) });
  return res;
}

const result = PRESETS.map(([label, seq]) => {
  setRot(seq);
  return { label, seq, ret: parseRet(out["#ret"]), shares: parseShares(out["#shares"]) };
});
fs.mkdirSync(path.join(__dirname, "fixtures"), { recursive: true });
fs.writeFileSync(path.join(__dirname, "fixtures", "site_presets.json"), JSON.stringify(result, null, 1), "utf8");
console.log(`OK: ${result.length} пресетів, рядків ret: ${result.map(r => r.ret.length).join(",")}`);
