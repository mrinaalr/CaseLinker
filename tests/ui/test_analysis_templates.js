#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(
  path.join(__dirname, "../../visualization/analysis.html"),
  "utf8"
);
const start = html.indexOf("<script>\n(function () {");
const end = html.lastIndexOf("})();");
if (start < 0 || end < 0) {
  console.error("could not find the ask script");
  process.exit(1);
}
let script = html.slice(start + "<script>\n".length, end);
script += "\nglobalThis.__askBuild = build;\n})();\n";

function el() {
  return {
    hidden: false,
    value: "",
    innerHTML: "",
    textContent: "",
    appendChild() {},
    addEventListener() {},
    classList: { add() {}, remove() {} },
    setAttribute() {},
  };
}
global.document = {
  getElementById: () => el(),
  createElement: () => el(),
  addEventListener() {},
};

eval(script);
const build = globalThis.__askBuild;

function sparql(q) {
  const t = build(q);
  if (!t) throw new Error("no template for: " + q);
  return t.sparql;
}

const notTip = sparql("Cases that do not involve a CyberTip");
if (!/FILTER NOT EXISTS \{ \?case uco-core:object \?noTip/.test(notTip)) {
  throw new Error("negation did not exclude a CyberTip:\n" + notTip);
}
if (/\?case uco-core:object \?tip \./.test(notTip)) {
  throw new Error("negation still requires a CyberTip:\n" + notTip);
}

const versus = sparql("Texas versus Florida");
if (!/FILTER\(\?st IN \("TX", "FL"\)\)/.test(versus) && !/FILTER\(\?st IN \("FL", "TX"\)\)/.test(versus)) {
  throw new Error("versus dropped a state:\n" + versus);
}

const perYear = sparql("How many sextortion cases are there per year");
if (!/GROUP BY \?year/.test(perYear)) {
  throw new Error("per year was not grouped:\n" + perYear);
}
if (/LIMIT 50/.test(perYear)) {
  throw new Error("per year is still a 50-case list:\n" + perYear);
}

const states = sparql("Which states have the most sextortion cases");
if (!/GROUP BY \?st/.test(states)) {
  throw new Error("which states was not grouped:\n" + states);
}

const district = sparql("How many cases in the Eastern District of Virginia");
if (!/jurisdiction\/eastern-district-of-virginia/.test(district)) {
  throw new Error("district fell through to the state:\n" + district);
}
if (/location\/[^"]*-va/.test(district)) {
  throw new Error("district still filters every Virginia place:\n" + district);
}

const west = sparql("How many cases in West Virginia");
if (!/-wv\(/.test(west)) {
  throw new Error("West Virginia collapsed to Virginia:\n" + west);
}

const list = build("sextortion cases");
if (!list || list.limited !== 50) {
  throw new Error("case list does not say it stops at 50");
}

const posPlace = (abbr) => new RegExp('\\?case dcterms:spatial \\?place \\. FILTER\\(REGEX\\(STR\\(\\?place\\), "/location/\\[\\^/\\]\\*-' + abbr + '\\(');
const negPlace = (abbr) => new RegExp('FILTER NOT EXISTS \\{ \\?case dcterms:spatial \\?noPlace \\. FILTER\\(REGEX\\(STR\\(\\?noPlace\\), "/location/\\[\\^/\\]\\*-' + abbr + '\\(');
const posPlat = (slug) => new RegExp('\\n    <[^>]*/platform/' + slug + '> a cac-core:DigitalSystemEntity \\.');
const negPlat = (slug) => new RegExp('FILTER NOT EXISTS \\{ <[^>]*/platform/' + slug + '> a cac-core:DigitalSystemEntity');

const tipFl = sparql("cases without a CyberTip in Florida");
if (!/FILTER NOT EXISTS \{ \?case uco-core:object \?noTip/.test(tipFl)) throw new Error("without a CyberTip did not exclude the CyberTip:\n" + tipFl);
if (!posPlace("fl").test(tipFl) || negPlace("fl").test(tipFl)) throw new Error("Florida was negated with the CyberTip:\n" + tipFl);

const snapTx = sparql("Sextortion cases that do not involve Snapchat in Texas");
if (!negPlat("snapchat").test(snapTx)) throw new Error("Snapchat was not excluded:\n" + snapTx);
if (!posPlace("tx").test(snapTx) || negPlace("tx").test(snapTx)) throw new Error("Texas was negated with Snapchat:\n" + snapTx);

const notTx = build("Cases not in Texas involving Snapchat");
if (!negPlace("tx").test(notTx.sparql)) throw new Error("not in Texas did not exclude Texas:\n" + notTx.sparql);
if (!posPlat("snapchat").test(notTx.sparql) || negPlat("snapchat").test(notTx.sparql)) throw new Error("Snapchat was negated with Texas:\n" + notTx.sparql);
if (!/not Texas/.test(notTx.how)) throw new Error("excluded state is not labeled 'not Texas': " + notTx.how);

console.log("ask templates ok");
